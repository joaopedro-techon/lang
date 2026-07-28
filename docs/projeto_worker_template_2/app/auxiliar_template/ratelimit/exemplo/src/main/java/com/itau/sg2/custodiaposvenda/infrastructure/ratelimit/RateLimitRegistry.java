package com.itau.sg2.custodiaposvenda.infrastructure.ratelimit;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.cloud.context.scope.refresh.RefreshScopeRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Mantem o snapshot vigente da configuracao de rate limit e o recarrega quando o
 * config server muda.
 *
 * <p>Fluxo do reload: {@code /actuator/refresh} (ou spring-cloud-bus) dispara
 * {@code EnvironmentChangeEvent}, o Spring Cloud reassocia o
 * {@link RateLimitProperties}, e so entao chega o
 * {@link RefreshScopeRefreshedEvent} -- que e onde este bean escuta. Escutar o
 * evento tardio evita a corrida de ler propriedades ainda nao reassociadas.
 */
public class RateLimitRegistry implements InitializingBean {

    private static final Logger log = LoggerFactory.getLogger(RateLimitRegistry.class);

    private final RateLimitProperties properties;
    private final BucketFactory bucketFactory;
    private final ObjectMapper objectMapper;

    /**
     * Volatile: escrito raramente (reload de configuracao) e lido em toda request.
     * A leitura e um simples read de campo -- sem lock, sem contencao entre as
     * threads do Tomcat.
     */
    private volatile RateLimitSnapshot snapshot;

    /** Ultimo JSON aplicado, para evitar rebuild quando o refresh nao mexeu no rate limit. */
    private volatile String appliedJson;

    public RateLimitRegistry(RateLimitProperties properties,
                             BucketFactory bucketFactory,
                             ObjectMapper objectMapper) {
        this.properties = properties;
        this.bucketFactory = bucketFactory;
        this.objectMapper = objectMapper;
    }

    @Override
    public void afterPropertiesSet() {
        reload();
    }

    /**
     * Executa por ultimo para garantir que o ConfigurationPropertiesRebinder ja
     * atualizou {@link RateLimitProperties}.
     */
    @EventListener(RefreshScopeRefreshedEvent.class)
    @Order(Ordered.LOWEST_PRECEDENCE)
    public void onRefresh() {
        reload();
    }

    RateLimitSnapshot currentSnapshot() {
        return snapshot;
    }

    /**
     * Reconstroi o snapshot a partir do JSON atual. Se o parse falhar, mantem o
     * snapshot anterior: uma configuracao malformada publicada no config server
     * nao pode derrubar o rate limit inteiro em 10 tasks de uma vez.
     */
    public synchronized void reload() {
        String json = properties.getConfigJson();

        if (json != null && json.equals(appliedJson) && snapshot != null) {
            log.debug("Rate limit: configuracao inalterada, reload ignorado");
            return;
        }

        Map<String, ClientRateLimit> parsed;
        try {
            parsed = parse(json);
        } catch (Exception e) {
            if (snapshot != null) {
                log.error("Rate limit: JSON invalido no config server, mantendo configuracao anterior "
                        + "({} clientes, versao {})", snapshot.size(), snapshot.getVersion(), e);
                return;
            }
            log.error("Rate limit: JSON invalido no config server e nao ha configuracao anterior. "
                    + "Subindo com configuracao vazia (politica para chave desconhecida: {})",
                    properties.getUnknownKeyPolicy(), e);
            parsed = Collections.emptyMap();
        }

        long version = properties.getConfigVersion() != null
                ? properties.getConfigVersion()
                : System.currentTimeMillis();

        Map<String, ClientRateLimit> effective = parsed;
        this.snapshot = new RateLimitSnapshot(
                effective,
                version,
                (bucketId, config) -> bucketFactory.create(bucketId, config, version));
        this.appliedJson = json;

        log.info("Rate limit carregado: {} api-keys, {} buckets distintos, versao {}",
                effective.size(),
                effective.values().stream()
                        .map(ClientRateLimit::getDynamicKeyRateLimitBucket)
                        .distinct()
                        .count(),
                version);
    }

    private Map<String, ClientRateLimit> parse(String json) throws Exception {
        if (json == null || json.trim().isEmpty()) {
            log.warn("Rate limit: app.rate-limit.config-json vazio");
            return Collections.emptyMap();
        }

        RateLimitConfigPayload payload = objectMapper.readValue(json, RateLimitConfigPayload.class);
        Map<String, ClientRateLimit> raw = payload.getRateLimitConfig();
        if (raw == null || raw.isEmpty()) {
            log.warn("Rate limit: no rateLimitConfig no payload");
            return Collections.emptyMap();
        }

        Map<String, ClientRateLimit> valid = new LinkedHashMap<>(raw.size() * 2);
        for (Map.Entry<String, ClientRateLimit> entry : raw.entrySet()) {
            ClientRateLimit config = entry.getValue();
            if (config != null && config.isValid()) {
                valid.put(entry.getKey(), config);
            } else {
                // Descartar so a entrada ruim e melhor do que rejeitar o arquivo
                // inteiro e deixar todos os clientes sem limite.
                log.warn("Rate limit: entrada invalida ignorada para api-key={} config={}",
                        entry.getKey(), config);
            }
        }
        return valid;
    }

    /** Raiz do payload do config server. */
    @JsonIgnoreProperties(ignoreUnknown = true)
    static final class RateLimitConfigPayload {

        private final Map<String, ClientRateLimit> rateLimitConfig;

        /**
         * {@code mode = PROPERTIES} e obrigatorio aqui. Um construtor de argumento
         * unico anotado apenas com {@code @JsonProperty} seria interpretado pelo
         * Jackson como <i>delegating</i>: ele tentaria desserializar o objeto
         * inteiro como o mapa, e o campo {@code rateLimitConfig} viraria uma
         * entrada do mapa em vez do envelope.
         */
        @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
        RateLimitConfigPayload(@JsonProperty("rateLimitConfig") Map<String, ClientRateLimit> rateLimitConfig) {
            this.rateLimitConfig = rateLimitConfig;
        }

        Map<String, ClientRateLimit> getRateLimitConfig() {
            return rateLimitConfig;
        }
    }
}
