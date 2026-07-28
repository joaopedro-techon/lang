package com.itau.sg2.custodiaposvenda;

import com.itau.sg2.custodiaposvenda.application.ports.outbound.IdempotenciaPort;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.localstack.LocalStackContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.sqs.SqsClient;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.testcontainers.containers.localstack.LocalStackContainer.Service.DYNAMODB;
import static org.testcontainers.containers.localstack.LocalStackContainer.Service.FIREHOSE;
import static org.testcontainers.containers.localstack.LocalStackContainer.Service.S3;
import static org.testcontainers.containers.localstack.LocalStackContainer.Service.SQS;

/**
 * Sobe o contexto Spring completo contra o LocalStack.
 * <p>
 * Sufixo {@code IT}: roda no failsafe, na fase {@code verify}, e não a cada {@code mvn test} —
 * subir container em todo build de unitário é caro demais para ser tolerado.
 * <p>
 * O teste mais importante aqui é o mais simples: <b>o contexto sobe</b>. Toda a revisão do
 * template foi verificada por compilação e testes de unidade, que não pegam erro de wiring —
 * bean faltando, dependência circular, property que não faz binding. É este teste que fecha
 * essa lacuna.
 */
/*
 * disabledWithoutDocker: sem Docker a classe inteira é PULADA, não quebrada. Um Docker Desktop
 * fora do ar na máquina de quem está desenvolvendo não pode reprovar o build.
 *
 * O contrapeso: no pipeline isso vira cobertura de integração ZERO, em silêncio, com o build
 * verde. Se o agente de CI não tiver Docker, este teste — que é o único que valida o wiring de
 * beans — nunca roda e ninguém fica sabendo. Confira os testes PULADOS no relatório do failsafe
 * antes de confiar num build verde.
 */
@Testcontainers(disabledWithoutDocker = true)
@SpringBootTest
class PedidoFluxoCompletoIT {

    private static final DockerImageName IMAGEM = DockerImageName.parse("localstack/localstack:3.8");

    @Container
    static final LocalStackContainer LOCALSTACK =
            new LocalStackContainer(IMAGEM).withServices(SQS, FIREHOSE, S3, DYNAMODB);

    @DynamicPropertySource
    static void propriedades(DynamicPropertyRegistry registry) {
        String endpoint = LOCALSTACK.getEndpoint().toString();

        registry.add("spring.cloud.aws.endpoint", () -> endpoint);
        registry.add("spring.cloud.aws.region.static", LOCALSTACK::getRegion);
        registry.add("spring.cloud.aws.credentials.access-key", LOCALSTACK::getAccessKey);
        registry.add("spring.cloud.aws.credentials.secret-key", LOCALSTACK::getSecretKey);

        registry.add("app.firehose.endpoint", () -> endpoint);
        registry.add("app.idempotencia.endpoint", () -> endpoint);

        registry.add("app.queue.pedido", () -> "pedido_queue");
        registry.add("app.queue.publicacao-sqs", () -> "publicacao_queue");
    }

    @Autowired
    private IdempotenciaPort idempotencia;

    @Autowired
    private SqsClient sqsClient;

    @Autowired
    private DynamoDbClient dynamoDbClient;

    @Test
    @DisplayName("o contexto Spring sobe com todos os beans resolvidos")
    void contextLoads() {
        assertNotNull(idempotencia, "IdempotenciaPort não foi resolvida");
        assertNotNull(sqsClient);
        assertNotNull(dynamoDbClient);
    }

    @Test
    @DisplayName("a segunda tentativa com a mesma chave é recusada")
    void idempotenciaRecusaDuplicata() {
        String chave = "pedido#1#PUBLICA_SQS";

        assertTrue(idempotencia.tentarIniciar(chave), "a primeira vez deve passar");
        assertFalse(idempotencia.tentarIniciar(chave), "a segunda vez deve ser recusada");

        idempotencia.liberar(chave);
        assertTrue(idempotencia.tentarIniciar(chave), "após liberar, deve voltar a passar");
    }

    /**
     * TODO: completar o fluxo ponta a ponta — publicar na fila, aguardar o consumo e verificar o
     * efeito no destino, além do caminho de DLQ com mensagem inválida. Depende de provisionar as
     * filas e streams no {@code @BeforeAll}, espelhando {@code localstack/init/01-recursos.sh}.
     */
    @Test
    @DisplayName("placeholder do fluxo fila -> Firehose e do caminho DLQ")
    void fluxoCompletoPendente() {
        assertTrue(List.of().isEmpty());
    }
}
