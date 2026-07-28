package com.itau.sg2.custodiaposvenda;

import com.itau.sg2.custodiaposvenda.application.facade.ProcessarPedidoFacade;
import org.junit.jupiter.api.BeforeAll;
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
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sns.SnsClient;
import software.amazon.awssdk.services.sns.model.SubscribeRequest;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.CreateQueueRequest;
import software.amazon.awssdk.services.sqs.model.GetQueueAttributesRequest;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.QueueAttributeName;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.testcontainers.containers.localstack.LocalStackContainer.Service.SNS;
import static org.testcontainers.containers.localstack.LocalStackContainer.Service.SQS;

/**
 * Sobe o contexto Spring completo contra o LocalStack e exercita o caminho que nenhum teste de
 * unidade alcança: a mensagem entrando pela fila de verdade e a publicação chegando ao destino.
 * <p>
 * Sufixo {@code IT}: roda no failsafe, na fase {@code verify}, e não a cada {@code mvn test} —
 * subir container em todo build é caro demais para ser tolerado.
 * <p>
 * O teste mais barato daqui é também o mais importante: <b>o contexto sobe</b>. Compilação não pega
 * erro de wiring — bean faltando, dependência circular, property que não faz binding. É este arquivo
 * que fecha essa lacuna.
 */
/*
 * disabledWithoutDocker: sem Docker a classe inteira é PULADA, não quebrada. Um Docker Desktop fora
 * do ar na máquina de quem está desenvolvendo não pode reprovar o build.
 *
 * O contrapeso: no pipeline isso vira cobertura de integração ZERO, em silêncio, com o build verde.
 * Se o agente de CI não tiver Docker, estes testes — os únicos que validam wiring de beans — nunca
 * rodam e ninguém fica sabendo. Confira os testes PULADOS no relatório do failsafe antes de confiar
 * num build verde.
 */
@Testcontainers(disabledWithoutDocker = true)
@SpringBootTest
class PedidoFluxoCompletoIT {

    private static final DockerImageName IMAGEM = DockerImageName.parse("localstack/localstack:3.8");

    private static final String FILA_ENTRADA = "pedido_queue";
    private static final String FILA_DLQ = "pedido_queue_dlq";
    private static final String FILA_SAIDA = "publicacao_queue";
    private static final String FILA_SONDA_SNS = "sns_sonda_queue";
    private static final String TOPICO = "pedido_topic";

    /** Tempo de espera das asserções assíncronas: o consumo da fila não é instantâneo. */
    private static final Duration ATE = Duration.ofSeconds(30);

    @Container
    static final LocalStackContainer LOCALSTACK =
            new LocalStackContainer(IMAGEM).withServices(SQS, SNS);

    private static SqsClient sqs;
    private static String urlFilaEntrada;
    private static String urlFilaDlq;
    private static String urlFilaSaida;
    private static String urlFilaSondaSns;
    private static String arnTopico;

    /**
     * Roda ANTES do contexto Spring subir — os callbacks do Testcontainers e este {@code @BeforeAll}
     * precedem a criação do contexto, que só acontece na preparação da primeira instância de teste.
     * A ordem não é detalhe: o listener sobe com {@code QueueNotFoundStrategy.FAIL} e o contexto não
     * carregaria se a fila ainda não existisse.
     */
    @BeforeAll
    static void provisionarRecursos() {
        sqs = cliente(SqsClient.builder()).build();

        try (SnsClient sns = cliente(SnsClient.builder()).build()) {
            urlFilaDlq = criarFila(FILA_DLQ, Map.of());

            String arnDlq = atributo(urlFilaDlq, QueueAttributeName.QUEUE_ARN);

            // Espelha o que o Terraform configura em dev/hom/prod. maxReceiveCount=1 apenas encurta
            // o teste: a aplicação não roteia nada para DLQ, quem encerra o ciclo é esta política.
            urlFilaEntrada = criarFila(FILA_ENTRADA, Map.of(
                    QueueAttributeName.VISIBILITY_TIMEOUT, "2",
                    QueueAttributeName.REDRIVE_POLICY,
                    "{\"deadLetterTargetArn\":\"" + arnDlq + "\",\"maxReceiveCount\":\"1\"}"));

            urlFilaSaida = criarFila(FILA_SAIDA, Map.of());
            urlFilaSondaSns = criarFila(FILA_SONDA_SNS, Map.of());

            arnTopico = sns.createTopic(builder -> builder.name(TOPICO)).topicArn();

            // Uma fila assinada ao tópico é o que permite afirmar que a publicação no SNS chegou a
            // algum lugar. RawMessageDelivery evita o envelope do SNS em volta do JSON do pedido.
            sns.subscribe(SubscribeRequest.builder()
                    .topicArn(arnTopico)
                    .protocol("sqs")
                    .endpoint(atributo(urlFilaSondaSns, QueueAttributeName.QUEUE_ARN))
                    .attributes(Map.of("RawMessageDelivery", "true"))
                    .returnSubscriptionArn(true)
                    .build());
        }
    }

    @DynamicPropertySource
    static void propriedades(DynamicPropertyRegistry registry) {
        String endpoint = LOCALSTACK.getEndpoint().toString();

        registry.add("spring.cloud.aws.endpoint", () -> endpoint);
        registry.add("spring.cloud.aws.region.static", LOCALSTACK::getRegion);
        registry.add("spring.cloud.aws.credentials.access-key", LOCALSTACK::getAccessKey);
        registry.add("spring.cloud.aws.credentials.secret-key", LOCALSTACK::getSecretKey);

        registry.add("app.firehose.endpoint", () -> endpoint);
        registry.add("app.firehose.delivery-stream-name", () -> "pedido-stream");

        registry.add("app.queue.pedido", () -> FILA_ENTRADA);
        registry.add("app.queue.publicacao-sqs", () -> FILA_SAIDA);

        // Resolvido em provisionarRecursos(), que roda antes da carga do contexto.
        registry.add("app.sns.topico-pedido", () -> arnTopico);
    }

    @Autowired
    private ProcessarPedidoFacade facade;

    @Test
    @DisplayName("o contexto Spring sobe com todos os beans resolvidos")
    void contextLoads() {
        assertNotNull(facade, "ProcessarPedidoFacade não foi resolvida");
    }

    @Test
    @DisplayName("fluxo PUBLICA_SQS: mensagem na fila de entrada -> fila de saída")
    void fluxoPublicaSqs() {
        enviar(mensagem("C-1", "P-1", "PUBLICA_SQS"));

        await().atMost(ATE).untilAsserted(() ->
                assertTrue(corpoRecebido(urlFilaSaida).stream().anyMatch(corpo -> corpo.contains("P-1")),
                        "o pedido deve chegar à fila de saída"));
    }

    @Test
    @DisplayName("fluxo PUBLICA_SNS: mensagem na fila de entrada -> tópico SNS")
    void fluxoPublicaSns() {
        enviar(mensagem("C-2", "P-2", "PUBLICA_SNS"));

        await().atMost(ATE).untilAsserted(() ->
                assertTrue(corpoRecebido(urlFilaSondaSns).stream().anyMatch(corpo -> corpo.contains("P-2")),
                        "o pedido deve chegar a quem assina o tópico"));
    }

    /**
     * O caminho que garante que mensagem ruim não gira para sempre. A aplicação não move nada para a
     * DLQ: ela apenas não confirma, e a {@code redrivePolicy} da fila encerra o ciclo (ADR-0001).
     */
    @Test
    @DisplayName("mensagem inválida não é confirmada e a redrivePolicy a leva para a DLQ")
    void mensagemInvalidaVaiParaDlq() {
        enviar(mensagem("C-3", "P-3", "FLUXO_QUE_NAO_EXISTE"));

        await().atMost(Duration.ofSeconds(60)).untilAsserted(() ->
                assertTrue(corpoRecebido(urlFilaDlq).stream().anyMatch(corpo -> corpo.contains("P-3")),
                        "a mensagem inválida deve terminar na DLQ"));
    }

    private static String mensagem(String idCliente, String idPedido, String fluxo) {
        return ("{\"idCliente\":\"%s\",\"idPedido\":\"%s\",\"valorTotal\":199.90,"
                + "\"quantidadeItens\":3,\"canal\":\"APP\",\"fluxo\":\"%s\"}")
                .formatted(idCliente, idPedido, fluxo);
    }

    private static void enviar(String corpo) {
        sqs.sendMessage(SendMessageRequest.builder()
                .queueUrl(urlFilaEntrada)
                .messageBody(corpo)
                .build());
    }

    private static List<String> corpoRecebido(String urlFila) {
        return sqs.receiveMessage(ReceiveMessageRequest.builder()
                        .queueUrl(urlFila)
                        .maxNumberOfMessages(10)
                        .visibilityTimeout(0)
                        .build())
                .messages().stream()
                .map(Message::body)
                .toList();
    }

    private static String criarFila(String nome, Map<QueueAttributeName, String> atributos) {
        return sqs.createQueue(CreateQueueRequest.builder()
                .queueName(nome)
                .attributes(atributos)
                .build()).queueUrl();
    }

    private static String atributo(String urlFila, QueueAttributeName atributo) {
        return sqs.getQueueAttributes(GetQueueAttributesRequest.builder()
                        .queueUrl(urlFila)
                        .attributeNames(atributo)
                        .build())
                .attributes().get(atributo);
    }

    private static <B extends software.amazon.awssdk.awscore.client.builder.AwsClientBuilder<B, ?>> B cliente(B builder) {
        return builder
                .endpointOverride(URI.create(LOCALSTACK.getEndpoint().toString()))
                .region(Region.of(LOCALSTACK.getRegion()))
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create(LOCALSTACK.getAccessKey(), LOCALSTACK.getSecretKey())));
    }
}
