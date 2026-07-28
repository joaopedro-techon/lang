package com.itau.sg2.custodiaposvenda.infrastructure.adapters.inbound;

import com.itau.sg2.custodiaposvenda.application.facade.ProcessarPedidoFacade;
import com.itau.sg2.custodiaposvenda.domain.pedido.PedidoEvent;
import com.itau.sg2.custodiaposvenda.shared.logging.Logger;
import com.itau.sg2.custodiaposvenda.shared.logging.PayloadLog;
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

    /**
     * A mensagem só é confirmada no caminho de sucesso. Qualquer exceção propaga sem
     * {@code acknowledge}, e o SQS reentrega após o <i>visibility timeout</i> até a
     * {@code redrivePolicy} da fila mover a mensagem para a DLQ.
     * <p>
     * Não há roteamento para DLQ aqui de propósito: a política da fila cobre também as falhas que
     * acontecem antes deste método (JSON malformado, erro de conversão, processo encerrado) e
     * preserva a mensagem original byte a byte.
     */
    @SqsListener(
            value = "${app.queue.pedido}",
            maxConcurrentMessages = "${app.queue.pedido-max-concurrent:10}",
            acknowledgementMode = "MANUAL"
    )
    public void listen(@Payload PedidoEvent event, Acknowledgement ack) {
        Logger.info("Mensagem recebida da fila de pedidos",
                PayloadLog.de("idOperacao", event.idOperacao()).e("fluxo", event.fluxo()));

        event.validar();

        processarPedidoFacade.executar(event);

        ack.acknowledge();
    }
}
