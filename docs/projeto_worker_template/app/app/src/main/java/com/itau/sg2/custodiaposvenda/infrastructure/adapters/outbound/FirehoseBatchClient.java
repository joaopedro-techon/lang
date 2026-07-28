package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import com.itau.sg2.custodiaposvenda.shared.logging.Logger;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.SdkBytes;
import software.amazon.awssdk.services.firehose.FirehoseAsyncClient;
import software.amazon.awssdk.services.firehose.model.PutRecordBatchRequest;
import software.amazon.awssdk.services.firehose.model.PutRecordBatchResponse;
import software.amazon.awssdk.services.firehose.model.PutRecordBatchResponseEntry;
import software.amazon.awssdk.services.firehose.model.Record;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;

/**
 * Publicação em lote no Firehose respeitando os limites do serviço e reenviando os registros que
 * falham individualmente.
 * <p>
 * {@code PutRecordBatch} pode retornar HTTP 200 com parte dos registros rejeitados (tipicamente
 * throttling). Ignorar {@code failedPutCount} significa perda silenciosa de dados.
 */
@Component
public class FirehoseBatchClient {

    /** Limites do PutRecordBatch: 500 registros, 4 MiB por requisição, 1000 KiB por registro. */
    private static final int MAX_REGISTROS_POR_BATCH = 500;
    private static final long MAX_BYTES_POR_BATCH = 4L * 1024 * 1024;
    private static final int MAX_BYTES_POR_REGISTRO = 1000 * 1024;

    private final FirehoseAsyncClient firehoseAsyncClient;
    private final ObjectMapper objectMapper;
    private final FirehoseProperties firehoseProperties;

    public FirehoseBatchClient(FirehoseAsyncClient firehoseAsyncClient,
                               ObjectMapper objectMapper,
                               FirehoseProperties firehoseProperties) {
        this.firehoseAsyncClient = firehoseAsyncClient;
        this.objectMapper = objectMapper;
        this.firehoseProperties = firehoseProperties;
    }

    /**
     * Variante bloqueante. Desembrulha a {@link CompletionException} para que o chamador veja a
     * causa real — necessário para classificar a falha (permanente x transitória).
     */
    public <T> void enviarSincrono(String deliveryStreamName, List<T> eventos) {
        try {
            enviar(deliveryStreamName, eventos).join();
        } catch (CompletionException ex) {
            Throwable causa = ex.getCause() != null ? ex.getCause() : ex;
            if (causa instanceof RuntimeException runtimeException) {
                throw runtimeException;
            }
            throw new FirehosePublicacaoException(
                    "Falha ao publicar no Firehose. stream=" + deliveryStreamName, causa);
        }
    }

    public <T> CompletableFuture<Void> enviar(String deliveryStreamName, List<T> eventos) {
        if (eventos == null || eventos.isEmpty()) {
            return CompletableFuture.completedFuture(null);
        }

        List<RegistroDimensionado> registros = eventos.stream()
                .map(evento -> toRegistro(evento, deliveryStreamName))
                .toList();

        List<List<Record>> batches = particionar(registros);

        List<CompletableFuture<Void>> futures = batches.stream()
                .map(batch -> enviarComRetry(deliveryStreamName, batch, 1))
                .toList();

        return CompletableFuture.allOf(futures.toArray(new CompletableFuture[0]));
    }

    private CompletableFuture<Void> enviarComRetry(String deliveryStreamName, List<Record> batch, int tentativa) {
        PutRecordBatchRequest request = PutRecordBatchRequest.builder()
                .deliveryStreamName(deliveryStreamName)
                .records(batch)
                .build();

        return firehoseAsyncClient.putRecordBatch(request)
                .thenCompose(response -> tratarResponse(response, batch, deliveryStreamName, tentativa));
    }

    private CompletableFuture<Void> tratarResponse(PutRecordBatchResponse response,
                                                   List<Record> batch,
                                                   String deliveryStreamName,
                                                   int tentativa) {
        int falhas = response.failedPutCount() != null ? response.failedPutCount() : 0;

        if (falhas == 0) {
            Logger.info(String.format("Batch de %d records enviado com sucesso. stream=%s, tentativa=%d",
                    batch.size(), deliveryStreamName, tentativa));
            return CompletableFuture.completedFuture(null);
        }

        List<Record> naoEnviados = registrosNaoEnviados(batch, response);
        String primeiroErro = primeiroErro(response);

        if (tentativa >= firehoseProperties.getMaxTentativas()) {
            return CompletableFuture.failedFuture(new FirehosePublicacaoException(String.format(
                    "Firehose rejeitou %d de %d records após %d tentativas. stream=%s, primeiroErro=%s",
                    naoEnviados.size(), batch.size(), tentativa, deliveryStreamName, primeiroErro)));
        }

        long espera = backoffMillis(tentativa);

        Logger.warn(String.format(
                "Firehose rejeitou %d de %d records. stream=%s, tentativa=%d/%d, primeiroErro=%s. "
                        + "Reenviando em %dms.",
                naoEnviados.size(), batch.size(), deliveryStreamName, tentativa,
                firehoseProperties.getMaxTentativas(), primeiroErro, espera));

        return atraso(espera)
                .thenCompose(ignorado -> enviarComRetry(deliveryStreamName, naoEnviados, tentativa + 1));
    }

    /**
     * {@code requestResponses()} é posicionalmente correspondente aos registros enviados: a entrada
     * i traz o resultado do registro i. Só reenvia os que têm {@code errorCode}.
     */
    private List<Record> registrosNaoEnviados(List<Record> batch, PutRecordBatchResponse response) {
        List<PutRecordBatchResponseEntry> respostas = response.requestResponses();

        if (respostas == null || respostas.size() != batch.size()) {
            // Sem correspondência confiável, reenviar o batch inteiro é preferível a perder registros.
            return batch;
        }

        List<Record> naoEnviados = new ArrayList<>();
        for (int i = 0; i < batch.size(); i++) {
            if (respostas.get(i).errorCode() != null) {
                naoEnviados.add(batch.get(i));
            }
        }
        return naoEnviados;
    }

    private String primeiroErro(PutRecordBatchResponse response) {
        List<PutRecordBatchResponseEntry> respostas = response.requestResponses();

        if (respostas == null) {
            return "desconhecido";
        }

        return respostas.stream()
                .filter(entrada -> entrada.errorCode() != null)
                .findFirst()
                .map(entrada -> entrada.errorCode() + ": " + entrada.errorMessage())
                .orElse("desconhecido");
    }

    private long backoffMillis(int tentativa) {
        return firehoseProperties.getBackoffInicialMs() * (1L << (tentativa - 1));
    }

    private CompletableFuture<Void> atraso(long millis) {
        return CompletableFuture.runAsync(() -> {
        }, CompletableFuture.delayedExecutor(millis, TimeUnit.MILLISECONDS));
    }

    /**
     * Particiona respeitando simultaneamente o limite de registros e o de bytes por requisição.
     * Particionar apenas por contagem faz um lote de registros grandes ser rejeitado por inteiro.
     */
    private List<List<Record>> particionar(List<RegistroDimensionado> registros) {
        List<List<Record>> batches = new ArrayList<>();
        List<Record> atual = new ArrayList<>();
        long bytesAtual = 0;

        for (RegistroDimensionado registro : registros) {
            boolean estouraRegistros = atual.size() >= MAX_REGISTROS_POR_BATCH;
            boolean estouraBytes = !atual.isEmpty() && bytesAtual + registro.tamanhoBytes() > MAX_BYTES_POR_BATCH;

            if (estouraRegistros || estouraBytes) {
                batches.add(atual);
                atual = new ArrayList<>();
                bytesAtual = 0;
            }

            atual.add(registro.record());
            bytesAtual += registro.tamanhoBytes();
        }

        if (!atual.isEmpty()) {
            batches.add(atual);
        }

        return batches;
    }

    private <T> RegistroDimensionado toRegistro(T evento, String deliveryStreamName) {
        byte[] dados;
        try {
            dados = (objectMapper.writeValueAsString(evento) + "\n").getBytes(StandardCharsets.UTF_8);
        } catch (JacksonException e) {
            // No Jackson 3 esta exceção é unchecked, então o compilador não obriga mais este catch.
            // Ele continua aqui de propósito: sem ele, uma falha de serialização subiria como erro
            // genérico e perderia o nome do stream, que é o que localiza o problema.
            throw new FirehosePublicacaoException(
                    "Erro ao serializar evento para JSON. stream=" + deliveryStreamName, e);
        }

        if (dados.length > MAX_BYTES_POR_REGISTRO) {
            throw new FirehosePublicacaoException(String.format(
                    "Record de %d bytes excede o limite de %d bytes do Firehose. stream=%s",
                    dados.length, MAX_BYTES_POR_REGISTRO, deliveryStreamName));
        }

        return new RegistroDimensionado(
                Record.builder().data(SdkBytes.fromByteArray(dados)).build(),
                dados.length);
    }

    /** Evita recalcular/recopiar os bytes do {@link Record} durante o particionamento. */
    private record RegistroDimensionado(Record record, int tamanhoBytes) {
    }
}
