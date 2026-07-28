package com.itau.sg2.custodiaposvenda.infrastructure.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.regions.providers.AwsRegionProvider;
import software.amazon.awssdk.services.firehose.FirehoseClient;
import software.amazon.awssdk.services.firehose.FirehoseClientBuilder;

import java.net.URI;
import java.time.Duration;

/**
 * Cliente do Firehose.
 * <p>
 * Não há starter do Spring Cloud AWS para o Firehose, então este cliente é montado à mão — e por
 * isso fica de fora de tudo que o awspring configura para SQS e SNS. Daí repetir aqui,
 * explicitamente, o que lá vem de graça: credenciais e região dos beans do awspring,
 * {@code endpointOverride} para apontar ao LocalStack, e timeouts para que a chamada não segure uma
 * thread do listener indefinidamente.
 */
@Configuration
public class FirehoseConfig {

    @Bean
    public FirehoseClient firehoseClient(AwsCredentialsProvider credentialsProvider,
                                         AwsRegionProvider regionProvider,
                                         FirehoseProperties properties) {

        FirehoseClientBuilder builder = FirehoseClient.builder()
                .region(Region.of(regionProvider.getRegion().id()))
                .credentialsProvider(credentialsProvider)
                .overrideConfiguration(override -> override
                        .apiCallTimeout(Duration.ofSeconds(properties.getApiCallTimeoutSegundos()))
                        .apiCallAttemptTimeout(Duration.ofSeconds(properties.getApiCallAttemptTimeoutSegundos()))
                        .retryStrategy(retry -> retry.maxAttempts(properties.getMaxTentativas())));

        String endpoint = properties.getEndpoint();
        if (endpoint != null && !endpoint.isBlank()) {
            builder.endpointOverride(URI.create(endpoint));
        }

        return builder.build();
    }
}
