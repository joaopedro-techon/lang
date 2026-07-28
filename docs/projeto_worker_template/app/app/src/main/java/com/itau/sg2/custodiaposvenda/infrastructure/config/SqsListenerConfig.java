package com.itau.sg2.custodiaposvenda.infrastructure.config;

import com.itau.sg2.custodiaposvenda.infrastructure.adapters.inbound.SqsErrorHandler;
import com.itau.sg2.custodiaposvenda.infrastructure.adapters.inbound.SqsMdcInterceptor;
import io.awspring.cloud.sqs.config.SqsMessageListenerContainerFactory;
import io.awspring.cloud.sqs.listener.QueueNotFoundStrategy;
import io.awspring.cloud.sqs.listener.acknowledgement.handler.AcknowledgementMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;

/**
 * Factory dos containers de listener do SQS.
 * <p>
 * Estava no pacote {@code infrastructure.logging} — nada a ver com log; é configuração de
 * infraestrutura de mensageria.
 */
@Configuration
public class SqsListenerConfig {

    @Bean
    public SqsMessageListenerContainerFactory<Object> defaultSqsListenerContainerFactory(
            SqsAsyncClient sqsAsyncClient,
            SqsMdcInterceptor mdcInterceptor,
            SqsErrorHandler errorHandler) {

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
