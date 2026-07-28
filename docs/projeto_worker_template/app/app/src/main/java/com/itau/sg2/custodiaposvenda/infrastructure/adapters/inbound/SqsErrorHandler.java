package com.itau.sg2.custodiaposvenda.infrastructure.adapters.inbound;

import com.itau.sg2.custodiaposvenda.application.ports.outbound.MetricasPort;
import com.itau.sg2.custodiaposvenda.domain.pedido.exception.PedidoNaoProcessavelException;
import com.itau.sg2.custodiaposvenda.shared.logging.Logger;
import com.itau.sg2.custodiaposvenda.shared.logging.PayloadLog;
import io.awspring.cloud.sqs.listener.errorhandler.ErrorHandler;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

/**
 * Ponto único por onde passam todas as falhas dos listeners — inclusive as de conversão, que nunca
 * chegam ao caso de uso.
 * <p>
 * Era {@code PedidoQueueErrorHandler}: o nome prometia tratar a fila de pedidos, mas o handler é
 * registrado na factory e vale para <b>qualquer</b> listener da aplicação. As mensagens diziam
 * "fila pedido" independentemente da fila de origem, o que levaria a um diagnóstico errado assim
 * que o segundo listener existisse. O nome e as mensagens agora são genéricos, e a identificação
 * da mensagem vai no payload.
 * <p>
 * Este handler <b>observa</b>, não decide o destino da mensagem: ele não confirma nem descarta
 * nada. Como o listener só confirma no caminho de sucesso, a mensagem volta para a fila e é a
 * {@code redrivePolicy} (maxReceiveCount + deadLetterTargetArn, definida na infraestrutura) que
 * encerra o ciclo movendo-a para a DLQ.
 * <p>
 * A classificação permanente x transitória existe para alertabilidade: "chegou poison pill" e
 * "dependência caiu" exigem respostas operacionais diferentes.
 */
@Component
public class SqsErrorHandler implements ErrorHandler<Object> {

    private static final String APPROXIMATE_RECEIVE_COUNT = "ApproximateReceiveCount";
    private static final int MAX_PROFUNDIDADE_CAUSAS = 10;

    private final MetricasPort metricas;

    public SqsErrorHandler(MetricasPort metricas) { this.metricas = metricas; }

    @Override
    public void handle(Message<Object> message, Throwable throwable) {
        String receiveCount = extractReceiveCount(message);
        boolean permanente = isPermanente(throwable);
        Throwable causaRaiz = causaRaiz(throwable);

        metricas.incrementarContador(MetricasPort.PEDIDO_FALHA,
                MetricasPort.TAG_TIPO_FALHA,
                permanente ? MetricasPort.TIPO_FALHA_PERMANENTE : MetricasPort.TIPO_FALHA_TRANSITORIA,
                MetricasPort.TAG_EXCECAO, causaRaiz.getClass().getSimpleName());

        // O corpo da mensagem NÃO vai para o log. Numa falha de conversão ele é o payload cru da
        // fila — o evento inteiro, sem qualquer filtro, em ERROR/WARN. A redrivePolicy já preserva
        // a mensagem byte a byte na DLQ, que é de onde se investiga o caso; o log carrega apenas
        // o que permite localizá-la lá.
        PayloadLog contexto = PayloadLog.de("messageId", message.getHeaders().getId())
                .e("receiveCount", receiveCount)
                .e("causaRaiz", causaRaiz.getClass().getName());

        if (permanente) {
            Logger.error("Falha permanente ao processar mensagem: reentregar não resolve. "
                            + "A mensagem seguirá para a DLQ pela redrivePolicy da fila.",
                    contexto, throwable);
            return;
        }

        Logger.warn("Falha transitória ao processar mensagem: será reentregue pelo SQS.",
                contexto, throwable);
    }

    /**
     * Percorre a cadeia de causas: o framework embrulha a exceção do listener, então testar apenas
     * o {@code throwable} recebido classificaria toda falha permanente como transitória.
     */
    private boolean isPermanente(Throwable throwable) {
        Throwable atual = throwable;
        for (int i = 0; atual != null && i < MAX_PROFUNDIDADE_CAUSAS; i++) {
            if (atual instanceof PedidoNaoProcessavelException) {
                return true;
            }
            if (atual == atual.getCause()) {
                break;
            }
            atual = atual.getCause();
        }
        return false;
    }

    private Throwable causaRaiz(Throwable throwable) {
        Throwable atual = throwable;
        for (int i = 0; atual.getCause() != null && atual.getCause() != atual && i < MAX_PROFUNDIDADE_CAUSAS; i++) {
            atual = atual.getCause();
        }
        return atual;
    }

    private String extractReceiveCount(Message<Object> message) {
        Object value = message.getHeaders().get(APPROXIMATE_RECEIVE_COUNT);
        return value != null ? value.toString() : "unknown";
    }
}
