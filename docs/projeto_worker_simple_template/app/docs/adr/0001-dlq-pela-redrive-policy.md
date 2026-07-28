# ADR-0001 — A aplicação não roteia para DLQ

**Status:** aceito · **Data:** 2026-07-27

## Contexto

Uma mensagem que falha precisa sair do ciclo de reentrega em algum momento, senão o SQS a
reentrega para sempre. Havia duas formas de fazer isso: a aplicação publicar na DLQ ao classificar
a falha como permanente, ou a `redrivePolicy` da fila fazê-lo por `maxReceiveCount`.

A primeira versão implementava roteamento app-side, com um `PedidoDlqPublicador`.

## Decisão

O roteamento app-side foi removido. **A DLQ é responsabilidade exclusiva da `redrivePolicy`.**
A aplicação apenas deixa de confirmar a mensagem em caso de falha.

## Razões

- A `redrivePolicy` cobre falhas **anteriores** ao listener — JSON malformado, erro de conversão,
  processo encerrado no meio — onde não existe `catch` possível.
- Preserva a mensagem original byte a byte, com `messageId` e atributos. O roteamento app-side
  republicava o payload **re-serializado**; como `FAIL_ON_UNKNOWN_PROPERTIES` está desabilitado,
  campos não mapeados pelo record sumiriam da DLQ — exatamente os campos que se quer inspecionar
  ao investigar.
- Não exige permissão IAM de `SendMessage` na DLQ.
- Sem janela de inconsistência entre confirmar a mensagem e gravá-la na DLQ.
- Dois mecanismos criariam divergência silenciosa: um `app.queue.max-receive-count` e o
  `maxReceiveCount` da fila com valores diferentes → o menor vence e o outro vira código morto.

## Consequências

- **Pré-requisito de infraestrutura:** a fila DEVE ter `redrivePolicy`. Um projeto gerado sem ela
  fica **sem nenhuma** proteção contra poison pill. Documentado no `application.yml`, no javadoc
  do `SqsErrorHandler` e no README.
- Uma mensagem que comprovadamente nunca vai passar consome N ciclos de retry antes de cair na
  DLQ, em vez de sair na primeira entrega. Custo aceito.
- O listener **só confirma no caminho de sucesso**. É isso — e só isso — que garante a reentrega.
  Nenhum caminho de falha pode chamar `acknowledge()`.
- A validação de `PedidoEvent` é explícita (`validar()`), fora do construtor canônico. Lançar no
  construtor faria a falha ocorrer dentro da desserialização do Jackson, antes do listener: sem
  acesso ao `Acknowledgement`, a mensagem nunca seria confirmada nem roteada. Mesma razão para o
  `@JsonCreator` tolerante em `Fluxo`.
- O `SqsErrorHandler` classifica permanente x transitória apenas para **alertabilidade** — ele
  observa, não decide destino.
