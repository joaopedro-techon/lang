# ADR-0004 — Payload de log tipado

**Status:** aceito · **Data:** 2026-07-28

## Contexto

O campo `Payload` do log era `Object`. Passar o objeto de domínio inteiro era o caminho mais
curto, e era o que os call sites faziam — inclusive o error handler, que logava
`message.getPayload()`: o corpo cru da mensagem SQS, sem nenhum filtro, em ERROR/WARN.

Os tipos de domínio de hoje (`PedidoEvent`, `Pedido`) só têm `idOperacao` e `fluxo`, então não há
PII circulando. **O problema não é o dado de hoje.** É que todo projeto gerado a partir deste
template vai adicionar campos ao evento — CPF, conta, nome, valor — e todos passariam a ser
logados em INFO sem ninguém decidir isso. Num molde replicado por um gerador, o default é o
produto.

## Decisão

`Log.payload` é `PayloadLog`, um tipo que se monta **campo a campo**:

```java
Logger.info("Pedido processado",
        PayloadLog.de("idOperacao", pedido.idOperacao()).e("fluxo", pedido.fluxo()));
```

Nenhuma sobrecarga do `Logger` aceita `Object`.

## Razões

- Torna o vazamento **impossível por construção**, em vez de depender de disciplina ou de code
  review. Campo que ninguém nomeou não vaza.
- Não foi criada classe de máscaras (`Mascara.cpf()` etc.) de propósito: não há hoje campo
  sensível para mascarar, e a classe entraria como código morto. A regra de mascaramento é
  política de cada domínio — está documentada no javadoc do `PayloadLog`.
- `@JsonValue` mantém o formato do JSON idêntico ao anterior: nenhum parser a jusante quebra.
  A anotação vem de `com.fasterxml.jackson.annotation`, comum a Jackson 2 e 3 (ver ADR-0002).

## Consequências

- O corpo da mensagem **não** vai para o log em falha. Ele é preservado byte a byte na DLQ pela
  `redrivePolicy` (ADR-0001), que é de onde se investiga; o log carrega apenas `messageId`,
  `receiveCount` e a causa raiz — o suficiente para localizá-la lá.
- **Limite:** o tipo protege o campo `Payload`, não o `LogMessage`. `Logger.info("cpf=" + cpf)`
  continua possível e nenhum tipo impede. Só revisão ou uma regra ArchUnit pega isso.
