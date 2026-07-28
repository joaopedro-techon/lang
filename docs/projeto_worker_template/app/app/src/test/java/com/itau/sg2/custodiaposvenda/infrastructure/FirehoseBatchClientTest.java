package com.itau.sg2.custodiaposvenda.infrastructure;

import com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound.FirehoseBatchClient;
import com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound.FirehoseProperties;
import com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound.FirehosePublicacaoException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.services.firehose.FirehoseAsyncClient;
import software.amazon.awssdk.services.firehose.model.PutRecordBatchRequest;
import software.amazon.awssdk.services.firehose.model.PutRecordBatchResponse;
import software.amazon.awssdk.services.firehose.model.PutRecordBatchResponseEntry;
import software.amazon.awssdk.services.firehose.model.Record;
import tools.jackson.databind.json.JsonMapper;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.stream.IntStream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Cobre o particionamento e o retry parcial — a lógica onde um erro significa perda silenciosa de
 * dados, e que nunca foi exercitada.
 */
class FirehoseBatchClientTest {

    private static final String STREAM = "stream-teste";

    /** Registra as requisições recebidas e devolve a resposta programada para cada chamada. */
    static class FirehoseFake implements FirehoseAsyncClient {
        final List<PutRecordBatchRequest> requisicoes = new ArrayList<>();
        private final List<PutRecordBatchResponse> respostas;
        private int chamada = 0;

        FirehoseFake(List<PutRecordBatchResponse> respostas) { this.respostas = respostas; }

        @Override
        public CompletableFuture<PutRecordBatchResponse> putRecordBatch(PutRecordBatchRequest request) {
            requisicoes.add(request);
            PutRecordBatchResponse r = respostas.get(Math.min(chamada++, respostas.size() - 1));
            return CompletableFuture.completedFuture(r);
        }

        @Override public String serviceName() { return "firehose"; }

        @Override public void close() { }
    }

    private static PutRecordBatchResponse sucesso(int quantidade) {
        return PutRecordBatchResponse.builder()
                .failedPutCount(0)
                .requestResponses(IntStream.range(0, quantidade)
                        .mapToObj(i -> PutRecordBatchResponseEntry.builder().recordId("r" + i).build())
                        .toList())
                .build();
    }

    private static FirehoseProperties properties() {
        var p = new FirehoseProperties();
        p.setMaxTentativas(3);
        p.setBackoffInicialMs(1);
        return p;
    }

    private static FirehoseBatchClient client(FirehoseFake fake) {
        return new FirehoseBatchClient(fake, JsonMapper.builder().build(), properties());
    }

    @Test
    @DisplayName("501 registros são divididos em 2 batches, respeitando o limite de 500")
    void particionaPorContagem() {
        var fake = new FirehoseFake(List.of(sucesso(500), sucesso(1)));

        client(fake).enviarSincrono(STREAM, IntStream.range(0, 501).boxed().toList());

        assertEquals(2, fake.requisicoes.size());
        assertEquals(500, fake.requisicoes.get(0).records().size());
        assertEquals(1, fake.requisicoes.get(1).records().size());
    }

    @Test
    @DisplayName("nenhum batch excede 4 MiB, mesmo com poucos registros grandes")
    void particionaPorBytes() {
        // ~100 KiB cada: 60 registros passam de 4 MiB sem chegar perto de 500 itens.
        String grande = "x".repeat(100 * 1024);
        var eventos = IntStream.range(0, 60).mapToObj(i -> grande).toList();

        var fake = new FirehoseFake(List.of(sucesso(500)));
        client(fake).enviarSincrono(STREAM, eventos);

        assertTrue(fake.requisicoes.size() > 1,
                "esperava mais de um batch por causa do limite de bytes");

        long limite = 4L * 1024 * 1024;
        for (PutRecordBatchRequest req : fake.requisicoes) {
            long bytes = req.records().stream()
                    .mapToLong(r -> r.data().asByteArray().length)
                    .sum();
            assertTrue(bytes <= limite, "batch com " + bytes + " bytes excede 4 MiB");
        }
    }

    @Test
    @DisplayName("falha parcial reenvia apenas os registros rejeitados")
    void reenviaSomenteOsRejeitados() {
        // 1ª chamada: 3 registros, o do meio falha. 2ª chamada: sucesso.
        var parcial = PutRecordBatchResponse.builder()
                .failedPutCount(1)
                .requestResponses(
                        PutRecordBatchResponseEntry.builder().recordId("ok1").build(),
                        PutRecordBatchResponseEntry.builder()
                                .errorCode("ServiceUnavailable").errorMessage("slow down").build(),
                        PutRecordBatchResponseEntry.builder().recordId("ok3").build())
                .build();

        var fake = new FirehoseFake(List.of(parcial, sucesso(1)));
        client(fake).enviarSincrono(STREAM, List.of("a", "b", "c"));

        assertEquals(2, fake.requisicoes.size());
        assertEquals(3, fake.requisicoes.get(0).records().size());
        assertEquals(1, fake.requisicoes.get(1).records().size(),
                "só o registro rejeitado deve ser reenviado");

        Record reenviado = fake.requisicoes.get(1).records().getFirst();
        Record original = fake.requisicoes.get(0).records().get(1);
        assertEquals(original.data(), reenviado.data(),
                "o registro reenviado precisa ser exatamente o que falhou (índice 1)");
    }

    @Test
    @DisplayName("esgotar as tentativas falha em vez de descartar registros em silêncio")
    void esgotaTentativas() {
        var sempreFalha = PutRecordBatchResponse.builder()
                .failedPutCount(1)
                .requestResponses(PutRecordBatchResponseEntry.builder()
                        .errorCode("ServiceUnavailable").errorMessage("slow down").build())
                .build();

        var fake = new FirehoseFake(List.of(sempreFalha));

        var ex = assertThrows(FirehosePublicacaoException.class,
                () -> client(fake).enviarSincrono(STREAM, List.of("a")));

        assertEquals(3, fake.requisicoes.size(), "maxTentativas=3 deve produzir 3 chamadas");
        assertTrue(ex.getMessage().contains(STREAM), "a mensagem precisa dizer qual stream: " + ex.getMessage());
    }

    @Test
    @DisplayName("lista vazia não gera chamada")
    void listaVaziaNaoChama() {
        var fake = new FirehoseFake(List.of(sucesso(0)));
        client(fake).enviarSincrono(STREAM, List.of());
        assertEquals(0, fake.requisicoes.size());
    }
}
