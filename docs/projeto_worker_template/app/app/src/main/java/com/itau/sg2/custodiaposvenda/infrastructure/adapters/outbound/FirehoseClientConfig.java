package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider;
import software.amazon.awssdk.http.crt.AwsCrtAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.regions.providers.AwsRegionProvider;
import software.amazon.awssdk.services.firehose.FirehoseAsyncClient;
import software.amazon.awssdk.services.firehose.FirehoseAsyncClientBuilder;

import java.net.URI;
import java.time.Duration;

/**
 * Cliente do Firehose.
 * <p>
 * Não há starter do Spring Cloud AWS para o Firehose, então este cliente é montado à mão — e por
 * isso ficava de fora de tudo que o awspring configura para SQS. As três correções aqui vêm daí:
 * <ul>
 *   <li><b>Credenciais e região vêm dos beans do awspring</b>, não de {@code @Value}. Antes a
 *       região era lida direto da property e as credenciais caíam na cadeia default do SDK,
 *       divergindo do que o SQS usava.</li>
 *   <li><b>{@code endpointOverride}</b> quando {@code app.firehose.endpoint} está preenchido —
 *       é o que permite apontar para o LocalStack e exercitar o fluxo fora da AWS.</li>
 *   <li><b>{@code overrideConfiguration}</b> com timeouts e teto de tentativas. Sem
 *       {@code apiCallTimeout}, o {@code join()} do publicador pode segurar uma thread do
 *       listener indefinidamente.</li>
 * </ul>
 */
@Configuration
public class FirehoseClientConfig {

    @Bean
    public FirehoseAsyncClient firehoseAsyncClient(AwsCredentialsProvider credentialsProvider,
                                                   AwsRegionProvider regionProvider,
                                                   FirehoseProperties properties) {

        FirehoseAsyncClientBuilder builder = FirehoseAsyncClient.builder()
                .region(Region.of(regionProvider.getRegion().id()))
                .credentialsProvider(credentialsProvider)
                .httpClient(AwsCrtAsyncHttpClient.create())
                .overrideConfiguration(override -> override
                        .apiCallTimeout(Duration.ofSeconds(properties.getApiCallTimeoutSegundos()))
                        .apiCallAttemptTimeout(Duration.ofSeconds(properties.getApiCallAttemptTimeoutSegundos()))
                        // Consumer sobre a estratégia default do SDK: mantém o backoff da AWS e
                        // apenas limita as tentativas.
                        .retryStrategy(retry -> retry.maxAttempts(properties.getMaxTentativasSdk())));

        String endpoint = properties.getEndpoint();
        if (endpoint != null && !endpoint.isBlank()) {
            builder.endpointOverride(URI.create(endpoint));
        }

        return builder.build();
    }
}
