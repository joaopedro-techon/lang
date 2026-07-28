# Rate limit por api-key com Bucket4j — Spring Boot 2.7.2 / Java 11 / ECS Fargate

Rate limit por cliente (`x-itau-api-key`), configurado via config server, rodando em
**10 tasks Fargate** atrás de um ALB.

---

## 1. Por que precisa de estado compartilhado

A tentação óbvia é dividir a cota: 600 req/s ÷ 10 tasks = 60 req/s por task, buckets
em memória, latência zero. **Não funciona no seu caso**, e o motivo é o ALB.

O ALB distribui *conexões*, não requests. Com HTTP keep-alive e ~6 clientes, um cliente
que abre 4 conexões vai bater em, no máximo, 4 das 10 tasks — as outras 6 nunca veem
tráfego dele. Resultado: as 4 tasks rejeitam com 60 req/s cada (240 efetivos) enquanto
360 req/s de cota ficam parados nas tasks ociosas. O cliente leva 429 com menos de
metade da cota contratada.

Divisão local só é aceitável quando você tem muitos clientes com muitas conexões
efêmeras, e não é o caso aqui.

## 2. Por que não um round-trip por request

A alternativa ingênua é buckets no Redis com uma ida por request. Para um cliente de
600 req/s isso é 600 comandos/s **por bucket**, mais ~0,4–1 ms somados ao p50 de toda
request — inclusive das que seriam permitidas. O rate limit passa a ser o componente
mais caro do request path, o que é absurdo para algo que 99,9% do tempo só responde
"pode passar".

## 3. A solução: otimização preditiva do Bucket4j

`Optimizations.predicting(...)` mantém em cada task uma réplica local do bucket e só
conversa com o Redis quando uma das duas condições acontece:

- a task consumiu `maxUnsynchronizedTokens` desde o último sync, **ou**
- passou `maxUnsynchronizedTimeout` desde o último sync.

Entre os syncs, a decisão é local: um `tryConsume` em memória, sem rede, na casa dos
nanossegundos. O "predicting" ainda extrapola o ritmo de consumo dos outros nós entre
sincronizações, o que aperta o limite mais do que a otimização `delaying` pura.

### A matemática do overshoot

O limite superior conservador (o de `delaying`; `predicting` fica abaixo dele) é:

```
overshoot_max = numeroDeTasks × maxUnsynchronizedTokens
```

Invertendo, para escolher a reserva local a partir da tolerância que você aceita:

```
maxUnsynchronizedTokens = requestCount × tolerancia / numeroDeTasks
tokensDivisor           = numeroDeTasks / tolerancia
```

Com **10 tasks** e **10% de tolerância** → `tokensDivisor = 100`. É o default deste
exemplo. Para os clientes do seu JSON:

| requestCount | reserva local/task | overshoot máx. | % sobre a cota | comandos Redis/s por bucket |
|---:|---:|---:|---:|---:|
| 600 | 6  | 60 | 10% | ~100 (era 600) |
| 400 | 4  | 40 | 10% | ~100 (era 400) |
| 160 | 2  | 20 | 12,5% | ~80 (era 160) |
| 120 | 2  | 20 | 16,7% | ~60 (era 120) |

Cotas pequenas têm overshoot percentual maior por causa do piso
`min-unsynchronized-tokens: 2` — sem ele, um cliente de 120 req/s sincronizaria a cada
request e voltaríamos ao cenário do item 2. Se 16% for inaceitável para esses clientes,
baixe o piso para 1; você dobra as chamadas ao Redis desses buckets (que são baratos,
por serem os de menor volume).

**Não existe rate limit distribuído exato e barato ao mesmo tempo.** A pergunta certa
não é "como zerar o overshoot", é "quanto de overshoot o backend protegido aguenta".
Escolha a tolerância a partir daí.

## 4. Caminho quente

Uma request permitida executa:

1. `request.getHeader("x-itau-api-key")` — leitura de header já parseado;
2. leitura de um campo `volatile` (o snapshot de configuração) — sem lock;
3. `HashMap.get(apiKey)` — O(1), mapa imutável;
4. `ConcurrentHashMap.get(bucketId)` — O(1), sem lock no caso de acerto;
5. `bucket.tryConsumeAndReturnRemaining(1)` — local, sem rede em ~90% das vezes.

Sem alocação relevante, sem sincronização, sem I/O no caso comum.

Detalhes que importam:

- **`get` antes de `computeIfAbsent`** no cache de buckets: `computeIfAbsent` trava o
  bin do mapa mesmo quando a chave já existe, e aqui a chave existe em praticamente
  toda request.
- **Counters do Micrometer memoizados**: `meterRegistry.counter(...)` monta a lista de
  tags a cada chamada; em 600 rps isso é lixo de heap à toa.
- **Filtro cedo na cadeia** (`HIGHEST_PRECEDENCE + 20`): o ponto de rejeitar é não
  gastar thread, CPU e conexão de downstream. Depois dos filtros de MDC/correlação,
  para o 429 sair no log com trace-id.
- **Refill `greedy`, não `intervally`**: com `intervally` os 600 tokens voltariam de
  uma vez na virada do segundo, permitindo 1200 requests na fronteira entre janelas.
  `greedy` repõe continuamente (0,6 token/ms) e é o que o backend protegido de fato
  sente.

## 5. Configuração dinâmica sem redeploy

O JSON do config server vem como **string crua** em `app.rate-limit.config-json`, não
como `Map<String, ClientRateLimit>`. Motivo: o relaxed binding do Spring Boot normaliza
chaves de mapa não-colchetadas removendo hifens — e suas chaves são UUIDs
(`8f0e0b3d-efa1-...`). O binding direto mutilaria todas elas. Desserializar com Jackson
é imune a isso e casa 1:1 com o payload.

Fluxo do reload: `POST /actuator/refresh` (ou spring-cloud-bus) → `EnvironmentChangeEvent`
→ Spring Cloud reassocia `RateLimitProperties` → `RefreshScopeRefreshedEvent` → o
`RateLimitRegistry` reconstrói o snapshot. Escutar o evento tardio evita a corrida de
ler propriedades ainda não reassociadas.

A troca é **atômica**: monta-se um snapshot novo (mapa imutável + cache de buckets
vazio) e troca-se a referência `volatile`. Nenhuma request vê estado meio-atualizado, e
o cache velho vai junto com o snapshot velho — sem invalidação manual para dar errado.

### `config-version`

`app.rate-limit.config-version` alimenta o `withImplicitConfigurationReplacement` do
Bucket4j: quando a cota muda, a primeira task que enxergar a versão nova reescreve a
configuração no Redis preservando o consumo proporcional; tasks ainda desatualizadas
(versão menor) não regridem a configuração.

**Publique este valor junto com o JSON e incremente a cada alteração.** Se ficar nulo,
o código cai no epoch millis do carregamento — funciona, mas a task que reiniciar por
último sempre "vence", inclusive se estiver com configuração antiga.

## 6. Degradação

| Situação | Comportamento |
|---|---|
| Redis indisponível | `fail-open: true` → libera a request, incrementa `result=error`, loga em `warn` |
| JSON inválido no config server | mantém o snapshot anterior; nunca sobe configuração vazia por cima de uma boa |
| Entrada individual malformada | descarta só aquela api-key, preserva as demais |
| Api-key sem configuração | `unknown-key-policy` (`ALLOW` padrão / `DENY` → 429) |
| Header ausente | tratado como api-key desconhecida |

`fail-open` é a escolha certa aqui: rate limit é proteção, não regra de negócio. Um
failover de ElastiCache não pode virar indisponibilidade da API — e é por isso também
que `command-timeout` é 200 ms e não 3 s.

## 7. Arquivos

```
src/main/java/com/itau/sg2/custodiaposvenda/infrastructure/ratelimit/
├── RateLimitConfig.java        # wiring: RedisClient, ProxyManager, filtro
├── RateLimitProperties.java    # app.rate-limit.*
├── ClientRateLimit.java        # entrada do JSON do config server
├── RateLimitRegistry.java      # parse + snapshot + reload no refresh
├── RateLimitSnapshot.java      # config imutável + cache de buckets
├── BucketFactory.java          # Bandwidth/BucketConfiguration + otimização
├── RateLimiterService.java     # caminho quente + métricas + fail-open
├── RateLimitDecision.java
└── RateLimitFilter.java        # OncePerRequestFilter, 429 + headers

src/main/resources/application-ratelimit.yml
src/test/java/.../RateLimiterServiceTest.java
pom-snippet.xml
```

## 8. Instalação

1. Mescle `pom-snippet.xml` no seu `pom.xml`.
2. Copie o pacote `infrastructure.ratelimit` (ajuste o `package` se o seu for outro).
3. Mescle `application-ratelimit.yml` no seu `application.yml`.
4. Garanta que o config server publica `app.rate-limit.config-json` e
   `app.rate-limit.config-version`.
5. Aponte `app.rate-limit.redis.*` para o ElastiCache (`ssl: true` se houver
   encryption in-transit).

Em dev, sem Redis: `app.rate-limit.backend=LOCAL`.

## 9. Resposta ao cliente

```
HTTP/1.1 429 Too Many Requests
Retry-After: 1
X-RateLimit-Limit: 600
X-RateLimit-Remaining: 0
Content-Type: application/json

{"codigo":"RATE_LIMIT_EXCEEDED","mensagem":"Limite de requisicoes excedido para esta api-key.","limite":600,"tenteEmSegundos":1}
```

Requests permitidas também recebem `X-RateLimit-Limit` e `X-RateLimit-Remaining`.

## 10. Métricas

Counter `custom.sg2.dogstatsd.app.ratelimit` com tag `result` =
`allowed` | `rejected` | `error` | `unknown_key`, e tag `bucket` (nos dois primeiros).

Cardinalidade = número de buckets distintos — 6 no seu JSON, sem problema. Se essa
lista crescer para centenas, remova a tag `bucket` do caso `allowed` e mantenha só em
`rejected`.

Alertas que valem a pena: `rejected` subindo em um bucket específico (cliente
estourando cota ou cota mal dimensionada) e **qualquer** valor em `error` (Redis
degradado, com a API rodando sem proteção por causa do fail-open).

## 11. Pontos que dependem do seu ambiente — confira antes de subir

- **Versão do Bucket4j.** O exemplo usa `8.7.0` (baseline Java 11). As assinaturas
  usadas foram conferidas contra o código-fonte da tag `8.7.0`:
  `Optimizations.predicting(DelayParameters)`,
  `DelayParameters(long, Duration)`,
  `LettuceBasedProxyManager.builderFor(...)` e
  `io.github.bucket4j.distributed.ExpirationAfterWriteStrategy`.
  A API do pacote `distributed.proxy.optimization` mudou entre minors — se fixar outra
  versão, reconfira. Em particular, o overload de dois argumentos é
  `predicting(DelayParameters, PredictionParameters)`, **nessa ordem**.
- **Lettuce.** Spring Boot 2.7.2 gerencia 6.1.9.RELEASE; o `pom-snippet.xml` força
  6.2.6.RELEASE porque o `bucket4j-redis` 8.7.0 é compilado contra a linha 6.2.x.
  Sem isso o risco é `NoSuchMethodError` só sob carga.
- **ElastiCache cluster mode.** Suportado nos dois modos via
  `app.rate-limit.redis.cluster`: `false` usa `RedisClient` + endpoint primário,
  `true` usa `RedisClusterClient` + configuration endpoint.
- **Não compilei/rodei este código aqui** — o repositório atual é Spring Boot 4 /
  Java 25 e não teria como validar o alvo 2.7.2/11. Os testes em
  `RateLimiterServiceTest` rodam sem Redis (`backend=LOCAL`) e cobrem resolução de
  configuração, bucket compartilhado, reload e degradação; o comportamento distribuído
  precisa de um teste com Testcontainers Redis, que não está incluído.
