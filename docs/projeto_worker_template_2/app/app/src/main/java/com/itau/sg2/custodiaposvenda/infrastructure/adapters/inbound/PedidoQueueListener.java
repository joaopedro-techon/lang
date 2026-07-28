package com.itau.sg2.custodiaposvenda.infrastructure.adapters.inbound;

import com.itau.sg2.custodiaposvenda.application.facade.ProcessarPedidoFacade;
import com.itau.sg2.custodiaposvenda.domain.pedido.PedidoEvent;
import com.itau.sg2.custodiaposvenda.infrastructure.logging.Logger;
import io.awspring.cloud.sqs.annotation.SqsListener;
import io.awspring.cloud.sqs.listener.acknowledgement.Acknowledgement;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class PedidoQueueListener {

    private final ProcessarPedidoFacade processarPedidoFacade;

    public PedidoQueueListener(ProcessarPedidoFacade processarPedidoFacade) {
        this.processarPedidoFacade = processarPedidoFacade;
    }

    @SqsListener(
            value = "${app.queue.pedido}",
            maxConcurrentMessages = "${app.queue.pedido-max-concurrent:10}",
            acknowledgementMode = "MANUAL"
    )
    public void listen(@Payload PedidoEvent event, Acknowledgement ack) {
        Logger.info("Mensagem recebida da fila pedido_queue", event);

        processarPedidoFacade.executar(event);

        ack.acknowledge();
    }
}
