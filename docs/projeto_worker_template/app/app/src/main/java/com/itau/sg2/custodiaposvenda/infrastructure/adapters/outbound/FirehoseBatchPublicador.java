package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import com.itau.sg2.custodiaposvenda.application.ports.outbound.PublicadorMensagemPort;
import com.itau.sg2.custodiaposvenda.domain.pedido.Pedido;
import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * Publica o pedido no delivery stream do Firehose.
 * <p>
 * "Batch" no nome vem da API {@code PutRecordBatch} usada pelo {@link FirehoseBatchClient} — que
 * particiona os registros respeitando os limites do serviço — e não de agrupar vários pedidos.
 * O consumo da fila é mensagem a mensagem. O nome acompanha o fluxo
 * {@link Fluxo#DEMOCRATIZAR_FIREHOSE_BATCH}, que é contrato de mensagem e não pode ser renomeado.
 */
@Component
public class FirehoseBatchPublicador implements PublicadorMensagemPort {

    private final FirehoseBatchClient firehoseBatchClient;
    private final FirehoseProperties firehoseProperties;

    public FirehoseBatchPublicador(FirehoseBatchClient firehoseBatchClient,
                                   FirehoseProperties firehoseProperties) {
        this.firehoseBatchClient = firehoseBatchClient;
        this.firehoseProperties = firehoseProperties;
    }

    @Override
    public Fluxo fluxoSuportado() { return Fluxo.DEMOCRATIZAR_FIREHOSE_BATCH; }

    @Override
    public void publicar(Pedido pedido) {
        firehoseBatchClient.enviarSincrono(firehoseProperties.getDeliveryStreamName(), List.of(pedido));
    }
}
