package com.itau.sg2.custodiaposvenda.infrastructure.ratelimit;

import io.github.bucket4j.Bucket;
import io.github.bucket4j.ConsumptionProbe;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

/**
 * Avalia o rate limit de uma api-key. Este e o caminho quente: roda em toda
 * request, entao evita alocacao, lock e lookup desnecessario.
 */
public class RateLimiterService {

    private static final Logger log = LoggerFactory.getLogger(RateLimiterService.class);

    private static final String METRIC = "custom.sg2.dogstatsd.app.ratelimit";

    private final RateLimitRegistry registry;
    private final RateLimitProperties properties;
    private final MeterRegistry meterRegistry;

    /**
     * Counters memoizados por bucket. {@code MeterRegistry.counter()} faz lookup
     * e monta a lista de tags a cada chamada; em 600 rps isso vira lixo de heap
     * a toa.
     */
    private final Map<String, Counter> allowedCounters = new ConcurrentHashMap<>();
    private final Map<String, Counter> rejectedCounters = new ConcurrentHashMap<>();
    private final Counter errorCounter;
    private final Counter unknownKeyCounter;

    public RateLimiterService(RateLimitRegistry registry,
                              RateLimitProperties properties,
                              MeterRegistry meterRegistry) {
        this.registry = registry;
        this.properties = properties;
        this.meterRegistry = meterRegistry;
        this.errorCounter = meterRegistry.counter(METRIC, "result", "error");
        this.unknownKeyCounter = meterRegistry.counter(METRIC, "result", "unknown_key");
    }

    /**
     * @param apiKey valor do header {@code x-itau-api-key}; pode ser nulo.
     */
    public RateLimitDecision check(String apiKey) {
        if (!properties.isEnabled()) {
            return RateLimitDecision.notLimited();
        }

        RateLimitSnapshot current = registry.currentSnapshot();
        if (current == null) {
            return RateLimitDecision.notLimited();
        }

        ClientRateLimit config = apiKey == null ? null : current.configFor(apiKey);
        if (config == null) {
            unknownKeyCounter.increment();
            if (properties.getUnknownKeyPolicy() == RateLimitProperties.UnknownKeyPolicy.DENY) {
                return RateLimitDecision.rejected("unknown", 0, 1);
            }
            return RateLimitDecision.notLimited();
        }

        String bucketId = config.getDynamicKeyRateLimitBucket();
        try {
            Bucket bucket = current.bucketFor(config);
            ConsumptionProbe probe = bucket.tryConsumeAndReturnRemaining(1);

            if (probe.isConsumed()) {
                counter(allowedCounters, bucketId, "allowed").increment();
                return RateLimitDecision.allowed(bucketId, config.getRequestCount(), probe.getRemainingTokens());
            }

            counter(rejectedCounters, bucketId, "rejected").increment();
            return RateLimitDecision.rejected(bucketId, config.getRequestCount(),
                    retryAfterSeconds(probe.getNanosToWaitForRefill()));

        } catch (RuntimeException e) {
            errorCounter.increment();
            if (properties.isFailOpen()) {
                // Redis fora do ar nao pode virar indisponibilidade da API. Logamos
                // em warn (nao error) para nao inundar o alerta durante um failover
                // de ElastiCache, que e transitorio por natureza.
                log.warn("Rate limit indisponivel para bucket={}, liberando request (fail-open): {}",
                        bucketId, e.toString());
                return RateLimitDecision.notLimited();
            }
            throw e;
        }
    }

    /** Arredonda para cima: {@code Retry-After: 0} convidaria o cliente a repetir na hora. */
    private long retryAfterSeconds(long nanosToWait) {
        long seconds = TimeUnit.NANOSECONDS.toSeconds(nanosToWait);
        return TimeUnit.SECONDS.toNanos(seconds) < nanosToWait ? seconds + 1 : Math.max(1, seconds);
    }

    private Counter counter(Map<String, Counter> cache, String bucketId, String result) {
        Counter cached = cache.get(bucketId);
        if (cached != null) {
            return cached;
        }
        return cache.computeIfAbsent(bucketId,
                id -> meterRegistry.counter(METRIC, "result", result, "bucket", id));
    }
}
