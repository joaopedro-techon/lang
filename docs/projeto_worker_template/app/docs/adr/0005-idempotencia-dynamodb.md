# ADR-0005 — Idempotência sobre DynamoDB

**Status:** aceito · **Data:** 2026-07-28

## Contexto

SQS entrega **ao menos uma vez**. Duplicata não é caso raro: acontece sempre que o visibility
timeout expira antes da confirmação, quando a task é reciclada no meio do processamento, ou por
reentrega espontânea do próprio SQS. Sem controle, cada duplicata vira uma publicação duplicada no
destino — o problema nº 1 de um worker de fila.

O `RedisProperties` órfão no repositório sugeria que a idempotência via Redis tinha sido cogitada
e nunca implementada.

## Decisão

Tabela DynamoDB com chave `pedido#<idOperacao>#<fluxo>`, gravada por `PutItem` **condicional**
(`attribute_not_exists`), com TTL nativo.

## Razões

- A escrita condicional é **atômica**. É ela que serializa duas tasks recebendo a mesma duplicata
  ao mesmo tempo. Um `GetItem` seguido de `PutItem` teria uma janela entre as operações — que é
  exatamente o intervalo em que a duplicata chega.
- TTL nativo remove os registros sem job de limpeza.
- Não há cluster para operar, ao contrário de um Redis.
- O SDK cru basta: a única operação é um `PutItem` condicional. O
  `spring-cloud-aws-starter-dynamodb` traria cliente enhanced e mapeamento de entidades sem uso.

## O protocolo tem três passos, não um

```
tentarIniciar(chave)  → grava provisório (TTL curto). false = duplicata, descarta
   ... processa ...
concluir(chave)       → promove a definitivo (TTL longo). SÓ depois do sucesso
liberar(chave)        → remove a marca. No catch
```

`liberar` não é opcional. Marcar antes e não desmarcar na falha é o modo de falha mais perigoso
possível: a reentrega encontraria a chave marcada, seria descartada como duplicata, e a mensagem
**sumiria em silêncio** — sem ir para a DLQ, sem log de erro, sem métrica. Perda de dado
disfarçada de idempotência.

O TTL curto da marca provisória (300s) é a rede de segurança para o processo morrer entre iniciar
e concluir/liberar. Deve ser maior que o pior tempo de processamento e menor que o visibility
timeout da fila.

## A chave inclui o fluxo

A mesma operação pode legitimamente ser publicada em fluxos diferentes. Usar só o `idOperacao`
faria a segunda publicação ser descartada como duplicata.

## Consequências

- **A task role precisa de `dynamodb:PutItem` e `dynamodb:DeleteItem`.** As policies vivem nos
  JSON de `iamsr/policy/`. Sem elas a aplicação sobe e falha na primeira mensagem com
  `AccessDeniedException`.
- Uma chamada síncrona ao DynamoDB entra no caminho crítico de toda mensagem. Daí os timeouts
  curtos (5s de chamada, 2s por tentativa): um DynamoDB lento não pode virar fila parada.
- O TTL definitivo (72h) precisa cobrir a janela em que uma duplicata ainda pode chegar: retention
  da fila mais as reentregas até a DLQ.
- `app.idempotencia.ativa: false` desliga o controle. Significa **aceitar publicação duplicada**,
  não "sem efeito" — só faz sentido se o destino já for idempotente.
