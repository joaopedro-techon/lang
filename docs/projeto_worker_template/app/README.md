# msdemoworker

Worker de fila SQS. Consome mensagens de pedido, roteia por fluxo e publica no destino
correspondente (SQS ou Kinesis Firehose), gravando uma trilha de auditoria em paralelo.

Este repositório é um **template**: ele é replicado por um agente gerador para criar novos
projetos. Todo defeito aqui é herdado por todo projeto derivado — é o que justifica o rigor
das decisões registradas em [`docs/adr/`](docs/adr/).

## Rodando localmente

Pré-requisitos: JDK 25, Docker.

```bash
docker compose up -d          # LocalStack: filas, DLQ e delivery streams
cd app && ./mvnw spring-boot:run
```

O perfil `local` é o default (`spring.profiles.active` cai em `local` quando `ENVIRONMENT` não
está definida) e aponta todos os clientes AWS para o LocalStack em `localhost:4566`.

Publicar uma mensagem de teste:

```bash
aws --endpoint-url http://localhost:4566 sqs send-message \
  --queue-url http://localhost:4566/000000000000/pedido_queue \
  --message-body '{"idOperacao": 1, "fluxo": "PUBLICA_SQS"}'
```

Fluxos aceitos em `fluxo`: veja `domain/pedido/enums/Fluxo.java`. Valor desconhecido **não**
quebra a desserialização — vira `null` e é rejeitado por `PedidoEvent.validar()` como falha
permanente. Ver [ADR-0001](docs/adr/0001-dlq-pela-redrive-policy.md).

## Estrutura

```
app/src/main/java/com/itau/sg2/custodiaposvenda/
├── domain/           regras e tipos do negócio. Não depende de nada.
├── application/      casos de uso e PORTAS. Depende só de domain.
│   └── ports/        inbound (o que entra) e outbound (o que a aplicação precisa)
├── infrastructure/   ADAPTADORES. Implementa as portas. Conhece Spring, AWS, Jackson.
└── shared/           transversal (log). Pode ser usado por todas as camadas.
```

**A regra de dependência aponta para dentro.** `domain` não importa `application` nem
`infrastructure`; `application` não importa `infrastructure`. Quando a camada de dentro precisa de
algo de fora — métrica, execução assíncrona, auditoria — ela **declara uma porta** e a
infraestrutura implementa. Ver [ADR-0003](docs/adr/0003-regra-de-dependencia.md).

Verificação rápida (deve não retornar nada):

```bash
grep -rn "import com.itau.sg2.custodiaposvenda.infrastructure" app/src/main/java/com/itau/sg2/custodiaposvenda/{domain,application}
```

## Configuração

| Perfil | Quando | Destino AWS |
|---|---|---|
| `local` | desenvolvimento | LocalStack |
| `dev` / `hom` / `prod` | ECS | serviços reais, credenciais da task role |

O perfil vem da variável `ENVIRONMENT`, injetada pelo Terraform. Nomes de fila, streams e região
chegam por variável de ambiente — ver `infra/terraform/locals.tf`.

`server.port` é derivado de `task_container_port` no Terraform via `SERVER_PORT`, para que a
aplicação e o health check não possam divergir.

## Pré-requisito de infraestrutura

A fila de pedidos **DEVE** ter `redrivePolicy` com `maxReceiveCount` e `deadLetterTargetArn`.
A aplicação não roteia nada para DLQ: ela apenas deixa de confirmar a mensagem em caso de falha.
Sem a política, uma mensagem que sempre falha é reentregue indefinidamente.
Ver [ADR-0001](docs/adr/0001-dlq-pela-redrive-policy.md).

## Observabilidade

- Log estruturado JSON via `shared/logging/Logger`. O payload é tipado
  ([ADR-0004](docs/adr/0004-payload-de-log-tipado.md)) — objeto de domínio inteiro não entra.
- Métricas em statsd (sabor Datadog), atrás de `MetricasPort`.
- Probes: `/actuator/health/liveness` e `/actuator/health/readiness`.

## Idempotência

SQS entrega ao menos uma vez. A tabela DynamoDB `*-idempotencia` guarda a chave
`pedido#<idOperacao>#<fluxo>` com escrita condicional, o que impede que uma reentrega vire
publicação duplicada no destino.

O protocolo tem três passos — marcar, concluir **depois** do sucesso, liberar em caso de falha.
O passo de liberar não é opcional: sem ele, uma falha deixaria a chave marcada e a reentrega
seria descartada como duplicata, fazendo a mensagem sumir sem DLQ, sem log e sem métrica.

**Pré-requisito:** a task role precisa de `dynamodb:PutItem` e `dynamodb:DeleteItem` na tabela.

## Testes

```bash
cd app
./mvnw test      # unitários
./mvnw verify    # + testes de integração (*IT) com LocalStack via Testcontainers
```

O `RegraDeDependenciaTest` trava a regra de arquitetura do ADR-0003 — se alguém fizer
`application` importar `infrastructure`, o build reprova.

`jacoco:check` está com mínimo `0.00`: a cobertura ainda está longe do gate `Sonar-90` exigido
pelo pipeline. Subir o mínimo conforme a suíte crescer.

## Limitações conhecidas

- O fluxo ponta a ponta (fila → Firehose) e o caminho de DLQ no `PedidoFluxoCompletoIT` ainda são
  placeholder.
- Cobertura abaixo do gate `Sonar-90`.
