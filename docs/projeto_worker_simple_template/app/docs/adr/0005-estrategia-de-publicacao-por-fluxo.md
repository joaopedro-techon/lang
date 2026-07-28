# ADR-0005 — Estratégia de publicação escolhida pelo fluxo

**Status:** aceito · **Data:** 2026-07-28

## Contexto

O mesmo pedido pode precisar ir para destinos diferentes conforme quem o publicou: um tópico SNS
(fan-out para vários consumidores), uma fila SQS (entrega ponto a ponto para um serviço específico)
ou um delivery stream do Firehose (ingestão analítica). O campo `fluxo` da mensagem é quem diz qual.

A forma direta seria um `switch` no caso de uso. É também a que apodrece primeiro: cada destino novo
edita o mesmo método, os detalhes de três SDKs se acumulam numa classe só, e testar o roteamento
passa a exigir mocks de tudo que os `case` tocam.

## Decisão

Uma interface — `PublicadorPedidoPort` — com uma implementação por destino. Cada uma declara o fluxo
que atende em `fluxoSuportado()`; o Spring injeta todas como `List`, e o caso de uso as indexa num
`EnumMap<Fluxo, PublicadorPedidoPort>` no construtor.

```
PUBLICA_SNS      -> SnsPublicador
PUBLICA_SQS      -> SqsPublicador
PUBLICA_FIREHOSE -> FirehosePublicador
```

## Razões

- **Adicionar um destino é escrever uma classe.** Nenhum arquivo existente é editado — nem o caso de
  uso, nem um `switch`, nem uma fábrica. É o ponto do padrão.
- **A porta fica em `application`, as implementações em `infrastructure`.** O caso de uso conhece a
  interface e o enum; SNS, SQS e Firehose ficam do lado de fora (ADR-0003).
- **O índice é montado uma vez, no construtor**, e não a cada mensagem. De quebra, dois publicadores
  declarando o mesmo fluxo derrubam a aplicação **no startup**, com o nome das duas classes na
  mensagem — em vez de um deles vencer em silêncio conforme a ordem de injeção.
- **Fluxo declarado sem publicador é avisado no startup.** Sem isso, a falha só apareceria quando a
  primeira mensagem daquele tipo chegasse, em produção.

## Consequências

- `Fluxo` é **contrato de mensagem**: os nomes das constantes chegam como texto no JSON da fila.
  Renomear uma delas quebra todo produtor que já publica com o nome antigo.
- A cardinalidade é um destino por mensagem. Publicar no SNS **e** no Firehose para o mesmo pedido
  não cabe nesta estrutura — precisaria de um publicador composto, ou de a lista de destinos deixar
  de ser derivada de um único campo.
- Cada implementação carrega o erro do seu SDK. Nenhuma delas traduz falha de infraestrutura em
  exceção de domínio de propósito: falha de rede é transitória, e o `SqsErrorHandler` a classifica
  como tal para que a reentrega tenha efeito (ADR-0001).
