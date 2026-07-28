package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import com.itau.sg2.custodiaposvenda.application.ports.outbound.PublicadorPedidoPort;
import com.itau.sg2.custodiaposvenda.domain.pedido.Pedido;
import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;
import com.itau.sg2.custodiaposvenda.infrastructure.config.FirehoseProperties;
import com.itau.sg2.custodiaposvenda.shared.logging.Logger;
import com.itau.sg2.custodiaposvenda.shared.logging.PayloadLog;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.SdkBytes;
import software.amazon.awssdk.services.firehose.FirehoseClient;
import software.amazon.awssdk.services.firehose.model.PutRecordRequest;
import software.amazon.awssdk.services.firehose.model.Record;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.json.JsonMapper;

import java.nio.charset.StandardCharsets;

/**
 * Estratégia do fluxo {@link Fluxo#PUBLICA_FIREHOSE}: entrega o pedido a um delivery stream, que o
 * deposita no destino analítico (S3, Redshift, OpenSearch).
 * <p>
 * {@code PutRecord}, no singular, e não {@code PutRecordBatch}: o consumo da fila é mensagem a
 * mensagem, então um lote teria sempre um registro só — a complexidade de particionar por limite de
 * registros e de bytes existiria sem nunca ser exercitada. Se em algum projeto derivado houver
 * acúmulo real (consumo em batch, agregação por janela), aí sim o {@code PutRecordBatch} se paga —
 * junto com o tratamento de {@code failedPutCount}, que pode vir maior que zero <b>dentro de uma
 * resposta HTTP 200</b> e cuja ausência é perda silenciosa de dados.
 * <p>
 * O {@code \n} ao final de cada registro não é cosmético: sem ele os JSONs chegam concatenados no
 * arquivo do S3 e nenhum consumidor de JSON-lines consegue separá-los.
 */
@Component
public class FirehosePublicador implements PublicadorPedidoPort {

    /** Limite do serviço por registro: 1000 KiB. */
    private static final int MAX_BYTES_POR_REGISTRO = 1000 * 1024;

    private final FirehoseClient firehoseClient;
    private final JsonMapper jsonMapper;
    private final FirehoseProperties firehoseProperties;

    public FirehosePublicador(FirehoseClient firehoseClient,
                              JsonMapper jsonMapper,
                              FirehoseProperties firehoseProperties) {
        this.firehoseClient = firehoseClient;
        this.jsonMapper = jsonMapper;
        this.firehoseProperties = firehoseProperties;
    }

    @Override
    public Fluxo fluxoSuportado() {
        return Fluxo.PUBLICA_FIREHOSE;
    }

    @Override
    public void publicar(Pedido pedido) {
        String stream = firehoseProperties.getDeliveryStreamName();
        byte[] dados = serializar(pedido, stream);

        firehoseClient.putRecord(PutRecordRequest.builder()
                .deliveryStreamName(stream)
                .record(Record.builder().data(SdkBytes.fromByteArray(dados)).build())
                .build());

        Logger.info("Pedido publicado no Firehose",
                PayloadLog.de("idCliente", pedido.idCliente())
                        .e("idPedido", pedido.idPedido())
                        .e("stream", stream));
    }

    private byte[] serializar(Pedido pedido, String stream) {
        byte[] dados;
        try {
            dados = (jsonMapper.writeValueAsString(pedido) + "\n").getBytes(StandardCharsets.UTF_8);
        } catch (JacksonException ex) {
            // No Jackson 3 esta exceção é unchecked, então o compilador não obriga mais este catch.
            // Ele continua aqui de propósito: sem ele, uma falha de serialização subiria como erro
            // genérico e perderia o nome do stream, que é o que localiza o problema.
            throw new FirehosePublicacaoException(
                    "Erro ao serializar pedido para JSON. stream=" + stream, ex);
        }

        if (dados.length > MAX_BYTES_POR_REGISTRO) {
            throw new FirehosePublicacaoException(String.format(
                    "Record de %d bytes excede o limite de %d bytes do Firehose. stream=%s",
                    dados.length, MAX_BYTES_POR_REGISTRO, stream));
        }

        return dados;
    }
}
