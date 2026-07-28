package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import com.itau.sg2.custodiaposvenda.infrastructure.config.IdempotenciaProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.regions.providers.AwsRegionProvider;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.DynamoDbClientBuilder;

import java.net.URI;
import java.time.Duration;

/**
 * Cliente do DynamoDB para a tabela de idempotência.
 * <p>
 * Montado à mão, no mesmo padrão do {@link FirehoseClientConfig}, em vez de via
 * {@code spring-cloud-aws-starter-dynamodb}: o starter traz o cliente <i>enhanced</i>, mapeamento
 * de entidades e auto-configuração que não são usados aqui — a única operação é um
 * {@code PutItem} condicional.
 * <p>
 * Cliente <b>síncrono</b> de propósito: a checagem acontece antes de processar a mensagem e o
 * resultado é necessário imediatamente. Um cliente assíncrono só adicionaria um {@code join()}.
 */
@Configuration
public class DynamoDbClientConfig {

    @Bean
    public DynamoDbClient dynamoDbClient(AwsCredentialsProvider credentialsProvider,
                                         AwsRegionProvider regionProvider,
                                         IdempotenciaProperties properties) {

        DynamoDbClientBuilder builder = DynamoDbClient.builder()
                .region(Region.of(regionProvider.getRegion().id()))
                .credentialsProvider(credentialsProvider)
                .overrideConfiguration(override -> override
                        // Timeouts curtos: esta chamada está no caminho crítico de toda mensagem.
                        // Um DynamoDB lento não pode virar fila parada.
                        .apiCallTimeout(Duration.ofSeconds(5))
                        .apiCallAttemptTimeout(Duration.ofSeconds(2))
                        .retryStrategy(retry -> retry.maxAttempts(3)));

        String endpoint = properties.getEndpoint();
        if (endpoint != null && !endpoint.isBlank()) {
            builder.endpointOverride(URI.create(endpoint));
        }

        return builder.build();
    }
}
