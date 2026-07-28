# msdemoworker

Worker de fila SQS, escrito como **exemplo de arquitetura hexagonal**. O fluxo é curto de
propósito — o que está em exibição é a estrutura, não o negócio.

```
SQS (pedido_queue)
  │
  ├─ 1. loga o conteúdo de entrada
  ├─ 2. valida a mensagem
  ├─ 3. publica no destino do fluxo da mensagem
  │        PUBLICA_SNS      → tópico SNS
  │        PUBLICA_SQS      → fila SQS de saída
  │        PUBLICA_FIREHOSE → delivery stream do Firehose
  └─ 4. confirma a mensagem (ack)
```

Falhou em qualquer passo, a mensagem **não** é confirmada: o SQS reentrega e a `redrivePolicy` da
fila encerra o ciclo na DLQ ([ADR-0001](docs/adr/0001-dlq-pela-redrive-policy.md)).

Este repositório é um **template**: ele é replicado por um agente gerador para criar novos projetos.
Todo defeito aqui é herdado por todo projeto derivado — é o que justifica o rigor das decisões
registradas em [`docs/adr/`](docs/adr/).

## Rodando localmente

Pré-requisitos: JDK 25, Docker.

```bash
docker compose up -d          # LocalStack: filas, DLQ, tópico SNS e delivery stream
cd app && ./mvnw spring-boot:run
```

O perfil `local` é o default (`spring.profiles.active` cai em `local` quando `ENVIRONMENT` não está
definida) e aponta todos os clientes AWS para o LocalStack em `localhost:4566`.

```bash
# caminho feliz
aws --endpoint-url http://localhost:4566 sqs send-message \
  --queue-url http://localhost:4566/000000000000/pedido_queue \
  --message-body '{"idCliente":"C-1001","idPedido":"P-77","valorTotal":199.90,"quantidadeItens":3,"canal":"APP","fluxo":"PUBLICA_SNS"}'

# ver o resultado: a fila sonda está assinada ao tópico SNS
aws --endpoint-url http://localhost:4566 sqs receive-message \
  --queue-url http://localhost:4566/000000000000/sns_sonda_queue
```

Trocar `PUBLICA_SNS` por `PUBLICA_SQS` faz o pedido sair em `publicacao_queue`; por
`PUBLICA_FIREHOSE`, no bucket `msdemoworker-firehose`.

Para exercitar a DLQ, mande um `fluxo` desconhecido, um `valorTotal` zerado ou um campo obrigatório
ausente: os três são falhas **permanentes** e terminam em `pedido_queue_dlq`.

## Estrutura

```
app/src/main/java/com/itau/sg2/custodiaposvenda/
├── domain/           regras e tipos do negócio. Não depende de nada.
│   └── pedido/       PedidoEvent (entrada), Pedido (saída), Fluxo e exceções
├── application/      casos de uso e PORTAS. Depende só de domain.
│   ├── facade/       o que é transversal a todo processamento (métrica, log de desfecho)
│   ├── usecase/      a ordem das operações do fluxo
│   └── ports/        inbound (o que entra) e outbound (o que a aplicação precisa)
├── infrastructure/   ADAPTADORES. Implementa as portas. Conhece Spring, AWS, Jackson.
│   ├── adapters/     inbound (listener SQS) e outbound (SNS, SQS, Firehose)
│   └── config/       beans, clientes AWS e @ConfigurationProperties
└── shared/           transversal (log). Pode ser usado por todas as camadas.
```

**A regra de dependência aponta para dentro.** `domain` não importa `application` nem
`infrastructure`; `application` não importa `infrastructure`. Quando a camada de dentro precisa de
algo de fora — uma métrica, um destino de publicação — ela **declara uma porta** e a infraestrutura
implementa. Ver [ADR-0003](docs/adr/0003-regra-de-dependencia.md).

| Porta (application) | Adaptador (infrastructure) |
|---|---|
| `PublicadorPedidoPort` | `SnsPublicador`, `SqsPublicador`, `FirehosePublicador` |
| `MetricasPort` | `MicrometerMetricasAdapter` |

Adicionar um destino novo é escrever **uma classe** que implementa `PublicadorPedidoPort` e declara
o seu `Fluxo`. Nenhum arquivo existente é editado — nem o caso de uso, nem um `switch`.
Ver [ADR-0005](docs/adr/0005-estrategia-de-publicacao-por-fluxo.md).

Verificação rápida da regra (deve não retornar nada):

```bash
grep -rn "import com.itau.sg2.custodiaposvenda.infrastructure" app/src/main/java/com/itau/sg2/custodiaposvenda/{domain,application}
```

## Contrato da mensagem

```json
{
  "idCliente": "C-1001",
  "idPedido": "P-77",
  "valorTotal": 199.90,
  "quantidadeItens": 3,
  "canal": "APP",
  "fluxo": "PUBLICA_SNS"
}
```

`canal` é opcional; os demais são obrigatórios, e `valorTotal`/`quantidadeItens` precisam ser
maiores que zero. As invariantes vivem em `PedidoEvent.validar()`, não em anotações no adaptador de
entrada: valem para o pedido independentemente de ele ter chegado por SQS, por HTTP ou por um teste.

Um `fluxo` desconhecido **não** quebra a desserialização — vira `null` e é rejeitado por `validar()`
como falha permanente, já dentro do listener, onde a mensagem pode seguir o ciclo até a DLQ.

Os nomes das constantes de `Fluxo` são **contrato**: renomear quebra os produtores.

O que é publicado é `Pedido`, um tipo separado de `PedidoEvent` — um é o contrato de entrada, o
outro o de saída. Publicar o próprio evento recebido amarra os dois, e o dia em que a mensagem de
entrada ganhar um campo interno ele vaza para todos os consumidores.

## Configuração

| Perfil | Quando | Destino AWS |
|---|---|---|
| `local` | desenvolvimento | LocalStack |
| `dev` / `hom` / `prod` | ECS | serviços reais, credenciais da task role |

O perfil vem da variável `ENVIRONMENT`, injetada pelo Terraform. Nomes de fila, ARN do tópico,
stream e região chegam por variável de ambiente — ver `infra/terraform/locals.tf`.

`server.port` é derivado de `task_container_port` no Terraform via `SERVER_PORT`, para que a
aplicação e o health check não possam divergir.

## Pré-requisitos de infraestrutura

- A fila de pedidos **DEVE** ter `redrivePolicy` com `maxReceiveCount` e `deadLetterTargetArn`. A
  aplicação não roteia nada para DLQ: ela apenas deixa de confirmar a mensagem em caso de falha.
  Sem a política, uma mensagem que sempre falha é reentregue indefinidamente.
- A task role precisa de `sqs:ReceiveMessage`/`DeleteMessage`/`SendMessage`, `sns:Publish` e
  `firehose:PutRecord` — em `infra/terraform/iamsr/policy/policy-execution-ecs.json`. Sem elas a
  aplicação **sobe** e falha na primeira mensagem com `AccessDeniedException`.
- `app.sns.topico-pedido` é o **ARN completo**, não o nome do tópico: com o nome, o awspring
  precisaria de `sns:CreateTopic` para resolvê-lo.

## Observabilidade

- Log estruturado JSON via `shared/logging/Logger`. O payload é tipado
  ([ADR-0004](docs/adr/0004-payload-de-log-tipado.md)) — objeto de domínio inteiro não entra.
- Métricas em statsd (sabor Datadog), atrás de `MetricasPort`: duração e desfecho por fluxo, e
  falhas classificadas em permanente x transitória pelo `SqsErrorHandler`.
- Probes: `/actuator/health/liveness` e `/actuator/health/readiness`.

## Testes

```bash
cd app
./mvnw test      # RegraDeDependenciaTest (guarda o ADR-0003)
./mvnw verify    # + PedidoFluxoCompletoIT, com LocalStack via Testcontainers
```

Não há testes unitários neste template — a validação funcional é o `PedidoFluxoCompletoIT`, que sobe
o contexto inteiro contra o LocalStack e exercita a mensagem entrando pela fila, a publicação
chegando ao destino (SQS e SNS) e o caminho de DLQ.

## Limitações conhecidas

- **Sem controle de idempotência.** SQS entrega ao menos uma vez, então uma reentrega republica o
  pedido no destino. Aqui é inofensivo (mesmo payload), mas deixa de ser no momento em que o
  processamento tiver efeito acumulativo — debitar, contar, cobrar.
- **Sem persistência.** O worker não guarda estado: o pedido chega inteiro na mensagem e sai para o
  destino. Um repositório entra como porta em `application/ports/outbound` com adaptador em
  `infrastructure` — nunca com o domínio anotado pelo cliente do banco.
- `PedidoFluxoCompletoIT` é `@Testcontainers(disabledWithoutDocker = true)`: **sem Docker ele é
  pulado em silêncio**, com o build verde. Confira os testes PULADOS no relatório do failsafe.
- `jacoco:check` está com mínimo `0.00`, longe do gate `Sonar-90` exigido pelo pipeline.
- As policies IAM usam `Resource: "*"`. Restringir aos ARNs reais por ambiente.
