package com.itau.sg2.custodiaposvenda.infrastructure.ratelimit;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;

/**
 * Propriedades do rate limit.
 *
 * <p><b>Por que o JSON vem como String e nao como Map&lt;String, ClientRateLimit&gt;?</b>
 * O relaxed binding do Spring Boot normaliza chaves de mapa que nao estao entre
 * colchetes, removendo hifens. Como as chaves aqui sao UUIDs
 * ({@code 8f0e0b3d-efa1-...}), o binding direto mutilaria as chaves. Receber o
 * payload cru e desserializar com Jackson e imune a isso, casa 1:1 com o que o
 * config server devolve, e ainda permite versionar a configuracao por hash.
 */
@ConfigurationProperties(prefix = "app.rate-limit")
public class RateLimitProperties {

    public enum Backend {
        /** Buckets distribuidos no Redis/ElastiCache. Use em qualquer ambiente com mais de 1 task. */
        REDIS,
        /** Buckets em memoria, sem rede. Use apenas em dev/local ou single-task. */
        LOCAL
    }

    public enum UnknownKeyPolicy {
        /** Api-key sem configuracao passa direto (sem rate limit). */
        ALLOW,
        /** Api-key sem configuracao recebe 429. */
        DENY
    }

    private boolean enabled = true;

    private Backend backend = Backend.REDIS;

    private String headerName = "x-itau-api-key";

    /** Payload cru do config server: {"rateLimitConfig": { "<api-key>": {...} }}. */
    private String configJson;

    /**
     * Versao da configuracao. Deve ser <b>estritamente crescente</b> a cada
     * alteracao publicada no config server -- e o que decide qual task tem o
     * direito de reescrever a configuracao do bucket no Redis.
     *
     * <p>Se ficar nulo, cai no epoch millis do momento em que a task carregou a
     * configuracao. Funciona, mas tem um efeito colateral: a task que reiniciar
     * por ultimo sempre "vence", inclusive se estiver com configuracao antiga.
     * Em producao, prefira publicar este valor junto com o JSON.
     */
    private Long configVersion;

    private UnknownKeyPolicy unknownKeyPolicy = UnknownKeyPolicy.ALLOW;

    /**
     * Se true, uma falha no Redis libera a request (fail-open) em vez de derrubar
     * o trafego. Rate limit e protecao, nao regra de negocio: indisponibilidade do
     * Redis nao deve virar indisponibilidade da API.
     */
     private boolean failOpen = true;

    /** Prefixo das chaves no Redis. */
    private String keyPrefix = "rl:";

    /** Paths que nunca passam pelo filtro (health check do ALB, metricas). */
    private String[] excludedPaths = { "/actuator" };

    private final Sync sync = new Sync();

    private final Redis redis = new Redis();

    /**
     * Conexao com o ElastiCache. Fica aqui, e nao em {@code spring.redis.*}, para
     * o rate limit nao depender do spring-boot-starter-data-redis -- o Bucket4j
     * so precisa do lettuce-core.
     */
    public static class Redis {

        private String host = "localhost";
        private int port = 6379;
        private String password;
        /** ElastiCache com encryption in-transit exige true. */
        private boolean ssl = false;
        /**
         * true para ElastiCache com <i>cluster mode enabled</i> (usa o
         * configuration endpoint e RedisClusterClient); false para cluster mode
         * disabled (endpoint primario).
         */
        private boolean cluster = false;
        /**
         * Timeout de comando. Curto de proposito: com fail-open ligado, esperar
         * 3s pelo Redis e pior do que liberar a request.
         */
        private Duration commandTimeout = Duration.ofMillis(200);

        public String getHost() { return host; }

        public void setHost(String host) { this.host = host; }

        public int getPort() { return port; }

        public void setPort(int port) { this.port = port; }

        public String getPassword() { return password; }

        public void setPassword(String password) { this.password = password; }

        public boolean isSsl() { return ssl; }

        public void setSsl(boolean ssl) { this.ssl = ssl; }

        public boolean isCluster() { return cluster; }

        public void setCluster(boolean cluster) { this.cluster = cluster; }

        public Duration getCommandTimeout() { return commandTimeout; }

        public void setCommandTimeout(Duration commandTimeout) { this.commandTimeout = commandTimeout; }
    }

    /**
     * Parametros da sincronizacao local <-> Redis. Sao o coracao da performance:
     * ver README, secao "A matematica do overshoot".
     */
    public static class Sync {

        /**
         * Divisor aplicado sobre o {@code requestCount} do cliente para descobrir
         * quantos tokens cada task pode consumir localmente antes de sincronizar
         * com o Redis.
         *
         * <p>Formula: {@code divisor = numeroDeTasks / toleranciaDeOvershoot}.
         * Com 10 tasks e 10% de tolerancia -> 100. Para requestCount=600 isso da
         * 6 tokens por task sem sincronizar, ou seja, overshoot global de no
         * maximo 10 x 6 = 60 requests sobre 600.
         *
         * <p>Quanto maior o divisor, mais preciso o limite e mais chamadas ao Redis.
         */
        private int tokensDivisor = 100;

        /** Piso de tokens nao sincronizados, para nao zerar em cotas pequenas. */
        private long minUnsynchronizedTokens = 2;

        /** Teto de tokens nao sincronizados, para limitar o overshoot em cotas altas. */
        private long maxUnsynchronizedTokens = 20;

        /**
         * Tempo maximo que uma task segura tokens ja consumidos sem reportar ao
         * Redis. Baixar isso demais anula o ganho: com 100ms e reserva de 6
         * tokens, o que dispara primeiro em 60 rps/task e a reserva -- que e
         * exatamente o comportamento desejado.
         */
        private Duration maxUnsynchronizedTimeout = Duration.ofMillis(100);

        /** TTL da chave no Redis apos o ultimo write. */
        private Duration keyTtl = Duration.ofSeconds(30);

        public int getTokensDivisor() { return tokensDivisor; }

        public void setTokensDivisor(int tokensDivisor) { this.tokensDivisor = tokensDivisor; }

        public long getMinUnsynchronizedTokens() { return minUnsynchronizedTokens; }

        public void setMinUnsynchronizedTokens(long minUnsynchronizedTokens) {
            this.minUnsynchronizedTokens = minUnsynchronizedTokens;
        }

        public long getMaxUnsynchronizedTokens() { return maxUnsynchronizedTokens; }

        public void setMaxUnsynchronizedTokens(long maxUnsynchronizedTokens) {
            this.maxUnsynchronizedTokens = maxUnsynchronizedTokens;
        }

        public Duration getMaxUnsynchronizedTimeout() { return maxUnsynchronizedTimeout; }

        public void setMaxUnsynchronizedTimeout(Duration maxUnsynchronizedTimeout) {
            this.maxUnsynchronizedTimeout = maxUnsynchronizedTimeout;
        }

        public Duration getKeyTtl() { return keyTtl; }

        public void setKeyTtl(Duration keyTtl) { this.keyTtl = keyTtl; }
    }

    public boolean isEnabled() { return enabled; }

    public void setEnabled(boolean enabled) { this.enabled = enabled; }

    public Backend getBackend() { return backend; }

    public void setBackend(Backend backend) { this.backend = backend; }

    public String getHeaderName() { return headerName; }

    public void setHeaderName(String headerName) { this.headerName = headerName; }

    public String getConfigJson() { return configJson; }

    public void setConfigJson(String configJson) { this.configJson = configJson; }

    public Long getConfigVersion() { return configVersion; }

    public void setConfigVersion(Long configVersion) { this.configVersion = configVersion; }

    public UnknownKeyPolicy getUnknownKeyPolicy() { return unknownKeyPolicy; }

    public void setUnknownKeyPolicy(UnknownKeyPolicy unknownKeyPolicy) {
        this.unknownKeyPolicy = unknownKeyPolicy;
    }

    public boolean isFailOpen() { return failOpen; }

    public void setFailOpen(boolean failOpen) { this.failOpen = failOpen; }

    public String getKeyPrefix() { return keyPrefix; }

    public void setKeyPrefix(String keyPrefix) { this.keyPrefix = keyPrefix; }

    public String[] getExcludedPaths() { return excludedPaths; }

    public void setExcludedPaths(String[] excludedPaths) { this.excludedPaths = excludedPaths; }

    public Sync getSync() { return sync; }

    public Redis getRedis() { return redis; }
}
