# ADR-0002 — Jackson 3 como stack JSON da aplicação

**Status:** aceito · **Data:** 2026-07-28

## Contexto

Spring Boot 4.0.5 traz Jackson 3 (`tools.jackson`). O awspring 4.0.0 desativa o caminho Jackson 2
(`LegacySqsJackson2Configuration` é `@ConditionalOnMissingClass("tools.jackson...JsonMapper")`),
então o caminho ativo é `SqsJacksonConfiguration`.

Verificado no bytecode: esse caminho monta o conversor com
`jsonMapperProvider.getIfAvailable(JsonMapper::new)`.

O projeto declarava um `ObjectMapper` **do Jackson 2** como `@Primary`. Nenhum `JsonMapper`
existia no contexto → a fila caía no `new JsonMapper()` de defaults. Resultado:
`FAIL_ON_UNKNOWN_PROPERTIES`, `NON_NULL` e afins valiam para Firehose e auditoria, mas **não para
os payloads da fila** — duas stacks JSON com configurações que podiam divergir em silêncio.

## Decisão

Migrar a aplicação inteira para Jackson 3. O bean do `JacksonConfig` é um **`JsonMapper`** — o
tipo que o awspring procura. Como `JsonMapper extends ObjectMapper`, quem injeta `ObjectMapper`
recebe o mesmo bean.

Jackson 2 permanece no classpath **apenas** como dependência do logstash-logback-encoder, que
serializa os logs. Nenhum código da aplicação o referencia.

## Razões

- Acompanha o default do Boot 4 e do awspring 4, em vez de nadar contra ele a cada upgrade.
- Uma configuração só para fila, Firehose e auditoria.
- As duas stacks coexistem sem conflito: `jackson-annotations` 2.21 já contém `JsonSerializeAs`,
  a anotação que o databind 3.1.0 exige. Um único jar de annotations serve às duas.

## Consequências — diferenças de API que afetam quem mexer aqui

- O mapper é **imutável**: configuração só via `builder()`.
- `JavaTimeModule` não existe mais — suporte a `java.time` é embutido no databind 3.
- `WRITE_DATES_AS_TIMESTAMPS` e `ADJUST_DATES_TO_CONTEXT_TIME_ZONE` saíram de
  `Serialization/DeserializationFeature` para `tools.jackson.databind.cfg.DateTimeFeature`.
- `setSerializationInclusion` → `changeDefaultPropertyInclusion(UnaryOperator<JsonInclude.Value>)`.
- Exceções são **unchecked** (`JacksonException extends RuntimeException`). O compilador não
  obriga mais os `catch` que existiam — conferir antes de remover algum.
- Anotações continuam em `com.fasterxml.jackson.annotation`, comum às duas versões. É por isso que
  `@JsonCreator` no `Fluxo` e `@JsonValue` no `PayloadLog` funcionam independentemente da decisão.
