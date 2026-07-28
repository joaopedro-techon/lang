package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import com.itau.sg2.custodiaposvenda.application.ports.outbound.PublicadorMensagemPort;
import com.itau.sg2.custodiaposvenda.domain.pedido.Pedido;
import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;
import org.springframework.stereotype.Component;

import java.util.List;

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
    public void publicar(Pedido pedido) { publicar(List.of(pedido)); }

    @Override
    public void publicar(List<Pedido> pedidos) {
        firehoseBatchClient.enviar(firehoseProperties.getDeliveryStreamName(), pedidos).join();
    }
}
