package com.itau.sg2.custodiaposvenda.infrastructure.ratelimit;

import io.github.bucket4j.Bandwidth;
import io.github.bucket4j.Bucket;
import io.github.bucket4j.BucketConfiguration;
import io.github.bucket4j.Refill;
import io.github.bucket4j.TokensInheritanceStrategy;
import io.github.bucket4j.distributed.proxy.ProxyManager;
import io.github.bucket4j.distributed.proxy.optimization.DelayParameters;
import io.github.bucket4j.distributed.proxy.optimization.Optimizations;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

/**
 * Materializa buckets do Bucket4j a partir da configuracao de um cliente.
 *
 * <p>No backend REDIS o bucket e um {@code BucketProxy} com otimizacao
 * <b>preditiva</b>. Sem ela, cada request viraria um round-trip ao ElastiCache
 * (~0,5-1ms) e um cliente de 600 rps geraria 600 comandos/s por bucket. Com ela,
 * cada task consome tokens de uma reserva local e so conversa com o Redis quando
 * a reserva acaba ou o timeout estoura -- derrubando as chamadas em ~1-2 ordens
 * de grandeza. O preco e um overshoot pequeno e <i>limitado</i>; ver README.
 */
final class BucketFactory {

    private static final Logger log = LoggerFactory.getLogger(BucketFactory.class);

    private final RateLimitProperties properties;
    private final ProxyManager<byte[]> proxyManager;

    BucketFactory(RateLimitProperties properties, ProxyManager<byte[]> proxyManager) {
        this.properties = properties;
        this.proxyManager = proxyManager;
    }

    /**
     * @param configVersion versao do snapshot; usada para substituicao implicita
     *                      da configuracao no Redis quando o config server muda.
     */
    Bucket create(String bucketId, ClientRateLimit config, long configVersion) {
        BucketConfiguration bucketConfiguration = toBucketConfiguration(config);

        if (properties.getBackend() == RateLimitProperties.Backend.LOCAL || proxyManager == null) {
            log.info("Criando bucket LOCAL bucketId={} count={} seconds={}",
                    bucketId, config.getRequestCount(), config.getRequestSeconds());
            return Bucket.builder()
                    .addLimit(toBandwidth(config))
                    .build();
        }

        DelayParameters delayParameters = new DelayParameters(
                unsynchronizedTokens(config),
                properties.getSync().getMaxUnsynchronizedTimeout());

        byte[] key = (properties.getKeyPrefix() + bucketId).getBytes(StandardCharsets.UTF_8);

        log.info("Criando bucket REDIS bucketId={} count={} seconds={} tokensSemSync={} timeoutSync={}ms versao={}",
                bucketId, config.getRequestCount(), config.getRequestSeconds(),
                delayParameters.maxUnsynchronizedTokens,
                properties.getSync().getMaxUnsynchronizedTimeout().toMillis(),
                configVersion);

        return proxyManager.builder()
                // Overload de um argumento: usa PredictionParameters padrao,
                // derivado do proprio DelayParameters.
                .withOptimization(Optimizations.predicting(delayParameters))
                // Se o config server mudar a cota, a primeira task que enxergar a
                // versao nova reescreve a configuracao no Redis preservando o
                // consumo proporcional. Tasks ainda desatualizadas (versao menor)
                // nao regridem a configuracao.
                .withImplicitConfigurationReplacement(configVersion, TokensInheritanceStrategy.PROPORTIONALLY)
                .build(key, () -> bucketConfiguration);
    }

    private BucketConfiguration toBucketConfiguration(ClientRateLimit config) {
        return BucketConfiguration.builder()
                .addLimit(toBandwidth(config))
                .build();
    }

    /**
     * Refil <b>greedy</b> de proposito: com {@code intervally} os 600 tokens
     * voltariam todos de uma vez na virada do segundo, permitindo uma rajada de
     * 1200 requests na fronteira entre duas janelas. Greedy repoe continuamente
     * (0,6 token/ms para 600/s) e suaviza a curva -- que e o que o backend
     * protegido realmente sente.
     */
    private Bandwidth toBandwidth(ClientRateLimit config) {
        Duration period = Duration.ofSeconds(config.getRequestSeconds());
        return Bandwidth.classic(
                config.getRequestCount(),
                Refill.greedy(config.getRequestCount(), period));
    }

    /**
     * Quantos tokens uma task pode gastar sem consultar o Redis.
     * Escala com a cota do cliente e fica preso entre um piso e um teto, para que
     * cotas pequenas nao virem sync a cada request e cotas grandes nao gerem
     * overshoot desproporcional.
     */
    private long unsynchronizedTokens(ClientRateLimit config) {
        RateLimitProperties.Sync sync = properties.getSync();
        long scaled = config.getRequestCount() / Math.max(1, sync.getTokensDivisor());
        return Math.min(sync.getMaxUnsynchronizedTokens(),
                Math.max(sync.getMinUnsynchronizedTokens(), scaled));
    }
}
