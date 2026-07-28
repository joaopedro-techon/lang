package com.itau.sg2.custodiaposvenda.infrastructure.logging;

import com.itau.sg2.custodiaposvenda.infrastructure.adapters.inbound.PedidoQueueErrorHandler;
import io.awspring.cloud.sqs.config.SqsMessageListenerContainerFactory;
import io.awspring.cloud.sqs.listener.QueueNotFoundStrategy;
import io.awspring.cloud.sqs.listener.acknowledgement.handler.AcknowledgementMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;

@Configuration
public class SqsListenerConfig {

    @Bean
    public SqsMessageListenerContainerFactory<Object> defaultSqsListenerContainerFactory(
            SqsAsyncClient sqsAsyncClient,
            SqsMdcInterceptor mdcInterceptor,
            PedidoQueueErrorHandler errorHandler) {

        return SqsMessageListenerContainerFactory.builder()
                .sqsAsyncClient(sqsAsyncClient)
                .configure(options -> options
                        .queueNotFoundStrategy(QueueNotFoundStrategy.FAIL)
                        .acknowledgementMode(AcknowledgementMode.MANUAL))
                .messageInterceptor(mdcInterceptor)
                .errorHandler(errorHandler)
                .build();
    }
}
