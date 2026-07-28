# ADR-0003 — Regra de dependência e o pacote `shared`

**Status:** aceito · **Data:** 2026-07-28

## Contexto

O projeto declarava arquitetura hexagonal, mas a dependência apontava para fora:

- `ProcessarPedidoFacade` (application) importava `MetricsConfig`, `MdcAwareExecutor` e `Logger`
  de `infrastructure`;
- `AuditoriaContext` vivia em `domain` importando `ObjectMapper` e `MDC`, como singleton estático
  mutável;
- o caso de uso recebia de volta um `io.micrometer...Timer`, deixando o Micrometer vazar para
  dentro da camada de aplicação.

Para um template que é replicado por um gerador, isso é pior que um defeito local: ensina o
padrão errado a todo projeto derivado.

## Decisão

**A dependência aponta para dentro.** `domain` não importa `application` nem `infrastructure`;
`application` não importa `infrastructure`. Quando a camada de dentro precisa de algo de fora, ela
declara uma **porta** e a infraestrutura fornece o adaptador.

Portas criadas: `MetricasPort`, `ExecutorAssincronoPort`, `AuditoriaPort`.

Existe um quarto pacote, **`shared`**, que todas as camadas podem usar e que não depende de
nenhuma delas. Hoje contém apenas o log.

## Razões

- Log é preocupação transversal. As alternativas eram piores: deixá-lo em `infrastructure`
  mantinha a inversão; transformá-lo em porta injetada obrigaria a passar um logger por construtor
  em toda classe, inclusive nas de domínio, por um ganho de testabilidade que ninguém exerce.
- `MetricasPort.registrarTempo` recebe a ação em vez de devolver um cronômetro, justamente para
  que nenhum tipo do Micrometer atravesse a fronteira.
- `AuditoriaPort` elimina o estado estático global: o adaptador continua usando `ThreadLocal`
  (o modelo exige estado por thread), mas como bean, isolável em teste.

## Exceção consciente

`Fluxo` (domain) importa `com.fasterxml.jackson.annotation.JsonCreator`.

A tolerância a valor de enum desconhecido **precisa** estar no próprio enum: a desserialização
acontece antes do listener, e sem ela a mensagem quebraria no Jackson, fora de qualquer `catch`
com acesso ao `Acknowledgement` (ver ADR-0001). É uma anotação, não acoplamento comportamental, e
`jackson-annotations` é um jar só de anotações.

## Como isso é verificado

Hoje, por inspeção — não há teste. Deve virar uma regra ArchUnit junto com a suíte (item 37):

```bash
grep -rn "import com.itau.sg2.custodiaposvenda.infrastructure" \
  app/src/main/java/com/itau/sg2/custodiaposvenda/{domain,application}
```

Sem retorno = regra respeitada.
