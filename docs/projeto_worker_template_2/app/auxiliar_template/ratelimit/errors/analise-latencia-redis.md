# Análise: GET/EVAL em excesso no Redis e latência da API

**Serviço:** `sg2-custodiaposvenda-apiconsultaoperacoesposvenda`
**Sintoma:** trace do Datadog com centenas de spans `redis GET` / `redis EVAL` dentro de
uma única request; tempo de resposta degradado.
**Data da análise:** 2026-07-27
**Evidências:** prints em `auxiliar_template/ratelimit/errors/` (trace do Datadog,
`RateLimitInterceptor.java`, `BucketService.java`, config do `SpringDataRedisBasedProxyManager`).

---

## 1. Leitura correta do waterfall

Os números `546`, `9`, `535`, `534` ao lado dos spans no Datadog **não são IDs — são a
contagem de spans de cada subárvore**:

| Span | Spans na subárvore |
|---|---:|
| root (lambda `app-publicador-ressarcimentos`) | 546 |
| `POST /api/oauth/token` | 9 |
| `GET /posvenda/v1/operac...` | 535 |
| `sg2-custodiaposvenda-apiconsultaoperacoesposvenda` | **534** |

Ou seja: **~267 pares GET+EVAL dentro de uma única request HTTP**.

O badge `p57` indica que este trace está no percentil 57 da distribuição de latência —
é o **caso típico, não um outlier**. 2,84 s de latência mediana.

## 2. Por que GET+EVAL, e por que aos pares

O `SpringDataRedisBasedProxyManager` é um proxy manager **CAS** (compare-and-swap).
Uma tentativa de consumir token é sempre:

1. `GET` → lê o estado serializado do bucket
2. `EVAL` → script Lua que compara o estado lido com o atual e grava se ninguém mexeu

**O melhor caso possível já é 2 round-trips por request** (~4 ms neste trace, a ~1,9 ms
cada). Mas o trace mostra 267 pares, não 1.

O motivo está no core do Bucket4j (verificado no código-fonte da tag `8.7.0`,
`AbstractCompareAndSwapBasedProxyManager`):

```java
@Override
public <T> CommandResult<T> execute(K key, Request<T> request) {
    CompareAndSwapOperation operation = beginCompareAndSwapOperation(key);
    while (true) {                                    // ← sem limite de tentativas
        CommandResult<T> result = execute(request, operation);
        if (result != UNSUCCESSFUL_CAS_RESULT) {
            return result;
        }
    }                                                 // ← sem backoff
}
```

Loop infinito, sem backoff, sem teto. Cada volta = 1 GET + 1 EVAL. Quando o CAS falha
porque outra thread gravou primeiro, ele tenta de novo imediatamente.

Isso é um **livelock de CAS**: quanto mais concorrência na mesma chave, mais retries por
request — e mais retries geram mais contenção. A degradação é **quadrática, não linear**.
É por isso que a API "de repente" ficou lenta ao invés de piorar gradualmente.

## 3. Os quatro defeitos, em ordem de impacto

### 3.1. Uma única chave Redis absorve todo o tráfego

`BucketService.getRequestBucket(String apiKey)`:

```java
String bucketKey = "rateLimitConsulta:".concat(apiKey).concat(":").concat(dynamicKeyRateLimitBucket);
```

A chave é por api-key. Como o consumidor aqui é essencialmente **um** cliente (o lambda
`app-publicador-ressarcimentos`), 100% das requests concorrentes disputam **a mesma
chave**. É o pior cenário possível para CAS: toda a concorrência da API vira contenção
em um único ponto.

### 3.2. Nenhuma otimização configurada

```java
return this.proxyManager.builder()
    .withRecoveryStrategy(RecoveryStrategy.RECONSTRUCT)
    .build(bucketKey.getBytes(), getBucketConfiguration(rateLimit));
```

Não há `.withOptimization(...)`. O default é `NONE_OPTIMIZED`: **toda** request vai à
rede. Sem batching, sem reserva local, sem nada.

### 3.3. Um `BucketProxy` novo a cada request

`getRequestBucket()` reconstrói o proxy em toda chamada do `preHandle`.

Isso importa por um motivo não óbvio: **o estado das otimizações do Bucket4j vive dentro
da instância do `BucketProxy`**. Adicionar `.withOptimization(...)` sem cachear os proxies
**não resolve nada** — o estado local é descartado a cada request. Os consertos 3.2 e 3.3
são inseparáveis.

### 3.4. Uma única `RedisConnection` compartilhada por toda a aplicação

```java
@Bean
public SpringDataRedisBasedProxyManager redissonBasedProxyManager(RedisConnectionFactory lettuceConnectionFactory) {
    return SpringDataRedisBasedProxyManager.builderFor(lettuceConnectionFactory.getConnection())
        .withExpirationStrategy(ExpirationAfterWriteStrategy.basedOnTimeForRefillingBucketUpToMax(Duration.ofMinutes(15)))
        .build();
}
```

`getConnection()` é chamado **uma vez**, na criação do bean, e essa conexão é guardada
para sempre. Consequências:

- todas as threads do Tomcat usam a mesma instância de `RedisConnection`, que **não é
  thread-safe** pelo contrato do Spring Data;
- a conexão nunca é devolvida ao pool nem fechada;
- o tráfego fica serializado em uma conexão só;
- pior: o `GET` de uma thread pode ser invalidado pelo `EVAL` de outra, **alimentando o
  retry storm**.

Suspeito forte de ser o que transforma "algumas dezenas de retries" em 267.

## 4. Como confirmar objetivamente

Em ordem de custo. Os dois primeiros são decisivos e levam minutos:

1. **`CurrConnections` no CloudWatch do ElastiCache.** Se der ~1 conexão por task, o
   defeito 3.4 está confirmado na hora. Teste mais barato e mais conclusivo.
2. **Compare um trace de baixo tráfego com um de pico.** Se em baixa concorrência
   aparecer exatamente **1 GET + 1 EVAL** e no pico centenas → contenção de CAS
   confirmada. Se aparecerem centenas mesmo sem carga, o problema é outro (aí seria
   loop na aplicação).
3. **Filtre `redis.raw_command` / resource name dos spans** e verifique se todos apontam
   para a mesma chave `rateLimitConsulta:...`. Confirma o hot key (3.1).
4. **Métrica de EVAL/s no ElastiCache contra o RPS da API.** Se a razão for muito maior
   que 1, você está medindo o desperdício diretamente.

## 5. Direção da correção

| # | Defeito | Correção |
|---|---|---|
| 3.3 | `BucketProxy` recriado por request | Cachear os proxies por chave em `ConcurrentHashMap` |
| 3.2 | Sem otimização | `.withOptimization(Optimizations.predicting(...))` |
| 3.1 | Hot key única | Consequência das anteriores: menos idas ao Redis = menos CAS competindo |
| 3.4 | Conexão única compartilhada | Passar a `RedisConnectionFactory`, não uma `RedisConnection` capturada |

O ponto central: **3.1 não se resolve mudando a chave** — se há um cliente só, a chave é
uma só por definição. Resolve-se reduzindo drasticamente quantas requests chegam a fazer
CAS, que é exatamente o que a otimização preditiva faz (reserva local de tokens,
sincronização com o Redis a cada N tokens ou X ms).

Há uma implementação de referência completa dessa arquitetura em
`auxiliar_template/ratelimit/exemplo/` — o `README.md` de lá traz a matemática do
overshoot e os comentários em `RateLimitSnapshot`/`BucketFactory` explicam cada peça.

## 6. Pontos secundários (sem relação com latência)

- **`Refill.intervally`** em `getBucketConfiguration`: devolve todos os tokens de uma vez
  na virada da janela, permitindo rajada de 2× na fronteira entre dois períodos.
  `Refill.greedy` repõe continuamente e suaviza a curva.
- **`dynamicKeyRateLimitBucket` não agrupa nada**: como a chave inclui o `apiKey`, esse
  campo nunca chega a fazer duas api-keys compartilharem uma cota — que é exatamente para
  isso que ele existe no JSON do config server.
- **Possível NPE**: `quickConfigProperties.getRateLimitConfig(apiKey)` tem seu retorno
  usado direto em `rateLimit.getDynamicKeyRateLimitBucket()`. O `Optional.ofNullable`
  protege o *valor*, não o objeto — uma api-key desconhecida derruba a request com NPE
  em vez de cair num default.

## 7. Ressalvas

- A análise é baseada nos prints e no código-fonte público do Bucket4j 8.7.0. **Não
  executei nem instrumentei a aplicação.**
- O loop `while(true)` sem backoff é **fato verificado** no código-fonte.
- A atribuição dos 267 pares à contenção de CAS é **inferência** consistente com as
  evidências, mas o passo 4.2 (comparar traces de baixa vs. alta concorrência) é o que
  confirma de fato. Vale rodar antes de mexer no código.
