package com.itau.sg2.custodiaposvenda.infrastructure.logging;

import io.awspring.cloud.sqs.listener.interceptor.MessageInterceptor;
import org.slf4j.MDC;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@Component
public class SqsMdcInterceptor implements MessageInterceptor<Object> {

    private static final String CORRELATION_ID_ATTRIBUTE = "correlationid";
    private static final String TRANSACTION_ID_ATTRIBUTE = "transactionid";
    private static final String SIGLA_APP_ORIGEM_ATTRIBUTE = "siglaapporigem";
    private static final String CHANNEL_ATTRIBUTE = "channel";

    @Override
    public Message<Object> intercept(Message<Object> message) {
        Map<String, Object> headers = message.getHeaders();

        String correlationId = extractHeader(headers, CORRELATION_ID_ATTRIBUTE);
        String transactionId = extractHeader(headers, TRANSACTION_ID_ATTRIBUTE);
        String siglaApp = extractHeader(headers, SIGLA_APP_ORIGEM_ATTRIBUTE);
        String channel = extractHeader(headers, CHANNEL_ATTRIBUTE);

        MDC.put("CorrelationId", correlationId != null ? correlationId : UUID.randomUUID().toString());
        MDC.put("TransactionId", transactionId != null ? transactionId : UUID.randomUUID().toString());
        MDC.put("Channel", Optional.ofNullable(channel).orElse("N/A"));
        MDC.put("SiglaAppOrigem", Optional.ofNullable(siglaApp).orElse("N/A"));

        return message;
    }

    @Override
    public void afterProcessing(Message<Object> message, Throwable t) {
        MDC.remove("CorrelationId");
        MDC.remove("TransactionId");
        MDC.remove("Channel");
        MDC.remove("SiglaAppOrigem");
    }

    private String extractHeader(Map<String, Object> headers, String key) {
        for (Map.Entry<String, Object> entry : headers.entrySet()) {
            if (entry.getKey().equalsIgnoreCase(key) && entry.getValue() != null) {
                return entry.getValue().toString();
            }
        }
        return null;
    }
}
