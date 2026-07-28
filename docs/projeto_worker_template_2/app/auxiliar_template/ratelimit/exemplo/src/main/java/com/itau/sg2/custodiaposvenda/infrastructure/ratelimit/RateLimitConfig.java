package com.itau.sg2.custodiaposvenda.infrastructure.ratelimit;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.bucket4j.distributed.ExpirationAfterWriteStrategy;
import io.github.bucket4j.distributed.proxy.ProxyManager;
import io.github.bucket4j.redis.lettuce.cas.LettuceBasedProxyManager;
import io.lettuce.core.AbstractRedisClient;
import io.lettuce.core.RedisClient;
import io.lettuce.core.RedisURI;
import io.lettuce.core.cluster.RedisClusterClient;
import io.lettuce.core.codec.ByteArrayCodec;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

/**
 * Wiring do rate limit.
 */
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RateLimitProperties.class)
@ConditionalOnProperty(prefix = "app.rate-limit", name = "enabled", havingValue = "true", matchIfMissing = true)
public class RateLimitConfig {

    /**
     * Um unico bean para os dois modos do ElastiCache. O {@code shutdown()} do
     * cliente fecha as conexoes abertas a partir dele, entao nao ha bean separado
     * de conexao para vazar no shutdown da task.
     */
    @Bean(destroyMethod = "shutdown")
    @ConditionalOnProperty(prefix = "app.rate-limit", name = "backend", havingValue = "REDIS", matchIfMissing = true)
    public AbstractRedisClient rateLimitRedisClient(RateLimitProperties properties) {
        RateLimitProperties.Redis redis = properties.getRedis();

        RedisURI.Builder uri = RedisURI.builder()
                .withHost(redis.getHost())
                .withPort(redis.getPort())
                .withSsl(redis.isSsl())
                .withTimeout(redis.getCommandTimeout());

        if (redis.getPassword() != null && !redis.getPassword().trim().isEmpty()) {
            uri.withPassword(redis.getPassword().toCharArray());
        }

        return redis.isCluster()
                ? RedisClusterClient.create(uri.build())
                : RedisClient.create(uri.build());
    }

    @Bean
    @ConditionalOnProperty(prefix = "app.rate-limit", name = "backend", havingValue = "REDIS", matchIfMissing = true)
    public ProxyManager<byte[]> rateLimitProxyManager(AbstractRedisClient rateLimitRedisClient,
                                                      RateLimitProperties properties) {
        // Sem TTL, cada api-key que aparecer uma vez deixa lixo eterno no
        // ElastiCache. "up to max" expira a chave so depois que o bucket teria
        // voltado ao cheio -- expirar antes disso zeraria o consumo e daria cota
        // de graca a quem estivesse no limite.
        ExpirationAfterWriteStrategy expiration =
                ExpirationAfterWriteStrategy.basedOnTimeForRefillingBucketUpToMax(properties.getSync().getKeyTtl());

        // ByteArrayCodec: o Bucket4j serializa o estado do bucket em binario
        // proprio. Qualquer codec de String corromperia o payload.
        if (rateLimitRedisClient instanceof RedisClusterClient) {
            return LettuceBasedProxyManager
                    .builderFor(((RedisClusterClient) rateLimitRedisClient).connect(ByteArrayCodec.INSTANCE))
                    .withExpirationStrategy(expiration)
                    .build();
        }

        return LettuceBasedProxyManager
                .builderFor(((RedisClient) rateLimitRedisClient).connect(ByteArrayCodec.INSTANCE))
                .withExpirationStrategy(expiration)
                .build();
    }

    @Bean
    public BucketFactory rateLimitBucketFactory(RateLimitProperties properties,
                                                ObjectProvider<ProxyManager<byte[]>> proxyManager) {
        return new BucketFactory(properties, proxyManager.getIfAvailable());
    }

    @Bean
    public RateLimitRegistry rateLimitRegistry(RateLimitProperties properties,
                                               BucketFactory rateLimitBucketFactory,
                                               ObjectMapper objectMapper) {
        return new RateLimitRegistry(properties, rateLimitBucketFactory, objectMapper);
    }

    @Bean
    public RateLimiterService rateLimiterService(RateLimitRegistry rateLimitRegistry,
                                                 RateLimitProperties properties,
                                                 MeterRegistry meterRegistry) {
        return new RateLimiterService(rateLimitRegistry, properties, meterRegistry);
    }

    /**
     * Ordem alta na cadeia, mas nao a primeira: fica depois dos filtros de
     * correlacao/MDC para que um 429 ainda apareca no log com o trace-id da
     * request.
     */
    @Bean
    public FilterRegistrationBean<RateLimitFilter> rateLimitFilterRegistration(
            RateLimiterService rateLimiterService, RateLimitProperties properties) {

        FilterRegistrationBean<RateLimitFilter> registration =
                new FilterRegistrationBean<>(new RateLimitFilter(rateLimiterService, properties));
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 20);
        registration.addUrlPatterns("/*");
        registration.setName("rateLimitFilter");
        return registration;
    }
}
