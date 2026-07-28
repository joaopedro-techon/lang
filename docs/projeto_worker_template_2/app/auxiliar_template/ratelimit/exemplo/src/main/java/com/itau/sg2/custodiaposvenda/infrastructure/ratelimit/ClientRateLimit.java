package com.itau.sg2.custodiaposvenda.infrastructure.ratelimit;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Configuracao de rate limit de um unico cliente, exatamente como ela chega no
 * JSON do config server:
 *
 * <pre>
 * "8f0e0b3d-efa1-493f-91c1-34f38704dd4e": {
 *   "dynamicKeyRateLimitBucket": "019dc16f-870a-7c68-a692-4f0ed5e6cc45",
 *   "requestCount": "600",
 *   "requestSeconds": "1"
 * }
 * </pre>
 *
 * A chave do mapa e o valor do header {@code x-itau-api-key}. O
 * {@code dynamicKeyRateLimitBucket} identifica o bucket: duas api-keys que
 * apontarem para o mesmo bucket dividem a mesma cota.
 *
 * <p>Os numeros chegam como String no JSON; o Jackson faz a coercao para long
 * sem configuracao adicional.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public final class ClientRateLimit {

    private final String dynamicKeyRateLimitBucket;
    private final long requestCount;
    private final long requestSeconds;

    /**
     * {@code @JsonCreator} com {@code mode = PROPERTIES} e obrigatorio: sem ele o
     * Jackson nao usa um construtor multi-argumento de classe imutavel (nao ha
     * setters nem construtor padrao para o fallback).
     */
    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public ClientRateLimit(
            @JsonProperty("dynamicKeyRateLimitBucket") String dynamicKeyRateLimitBucket,
            @JsonProperty("requestCount") long requestCount,
            @JsonProperty("requestSeconds") long requestSeconds) {
        this.dynamicKeyRateLimitBucket = dynamicKeyRateLimitBucket;
        this.requestCount = requestCount;
        this.requestSeconds = requestSeconds;
    }

    public String getDynamicKeyRateLimitBucket() {
        return dynamicKeyRateLimitBucket;
    }

    public long getRequestCount() {
        return requestCount;
    }

    public long getRequestSeconds() {
        return requestSeconds;
    }

    boolean isValid() {
        return dynamicKeyRateLimitBucket != null
                && !dynamicKeyRateLimitBucket.trim().isEmpty()
                && requestCount > 0
                && requestSeconds > 0;
    }

    @Override
    public String toString() {
        return "ClientRateLimit{bucket=" + dynamicKeyRateLimitBucket
                + ", count=" + requestCount
                + ", seconds=" + requestSeconds + '}';
    }
}
