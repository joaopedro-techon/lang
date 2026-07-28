package com.itau.sg2.custodiaposvenda.infrastructure.adapters.inbound;

import com.itau.sg2.custodiaposvenda.application.facade.ProcessarPedidoFacade;
import com.itau.sg2.custodiaposvenda.domain.pedido.PedidoEvent;
import com.itau.sg2.custodiaposvenda.shared.logging.Logger;
import com.itau.sg2.custodiaposvenda.shared.logging.PayloadLog;
import io.awspring.cloud.sqs.annotation.SqsListener;
import io.awspring.cloud.sqs.listener.acknowledgement.Acknowledgement;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

/**
 * Adaptador de entrada: a fila SQS de pedidos.
 * <p>
 * Deliberadamente fino. Ele registra a chegada, valida a mensagem, delega e confirma — nenhuma regra
 * de negócio mora aqui, porque tudo que estivesse neste método só poderia ser testado subindo um
 * listener de SQS.
 */
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
     * preserva a mensagem original byte a byte. Ver ADR-0001.
     */
    @SqsListener(
            value = "${app.queue.pedido}",
            maxConcurrentMessages = "${app.queue.pedido-max-concurrent:10}",
            acknowledgementMode = "MANUAL"
    )
    public void listen(@Payload PedidoEvent event, Acknowledgement ack) {
        // O conteúdo de entrada, campo a campo. A mensagem inteira não é logada como objeto: é o que
        // faz um campo novo passar a ser registrado sem ninguém ter decidido isso (ADR-0004).
        Logger.info("Mensagem recebida da fila de pedidos",
                PayloadLog.de("idCliente", event.idCliente())
                        .e("idPedido", event.idPedido())
                        .e("valorTotal", event.valorTotal())
                        .e("quantidadeItens", event.quantidadeItens())
                        .e("canal", event.canal())
                        .e("fluxo", event.fluxo()));

        event.validar();

        processarPedidoFacade.executar(event);

        ack.acknowledge();
    }
}
