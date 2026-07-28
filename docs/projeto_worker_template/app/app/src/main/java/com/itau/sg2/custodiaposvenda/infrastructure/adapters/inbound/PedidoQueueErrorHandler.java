package com.itau.sg2.custodiaposvenda.infrastructure.adapters.inbound;

import com.itau.sg2.custodiaposvenda.infrastructure.logging.Logger;
import io.awspring.cloud.sqs.listener.errorhandler.ErrorHandler;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class PedidoQueueErrorHandler implements ErrorHandler<Object> {

    private static final String APPROXIMATE_RECEIVE_COUNT = "ApproximateReceiveCount";

    @Override
    public void handle(Message<Object> message, Throwable throwable) {
        String receiveCount = extractReceiveCount(message);

        Logger.error(
                String.format("Erro ao processar mensagem da fila pedido. receiveCount=%s, messageId=%s",
                        receiveCount, message.getHeaders().getId()),
                message.getPayload(),
                throwable
        );
    }

    private String extractReceiveCount(Message<Object> message) {
        Object value = message.getHeaders().get(APPROXIMATE_RECEIVE_COUNT);
        return value != null ? value.toString() : "unknown";
    }
}
