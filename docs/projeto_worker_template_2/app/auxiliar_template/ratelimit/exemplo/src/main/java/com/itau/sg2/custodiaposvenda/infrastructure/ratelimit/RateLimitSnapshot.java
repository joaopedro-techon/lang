package com.itau.sg2.custodiaposvenda.infrastructure.ratelimit;

import io.github.bucket4j.Bucket;

import java.util.Collections;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.BiFunction;

/**
 * Fotografia imutavel da configuracao de rate limit vigente.
 *
 * <p>Trocar a configuracao em runtime e feito trocando a referencia inteira do
 * snapshot (uma atribuicao volatile), nunca mutando o mapa. Com isso o caminho
 * quente do filtro nunca pega lock e nunca ve estado meio-atualizado.
 *
 * <p>O cache de buckets vive dentro do snapshot de proposito: ao trocar de
 * snapshot o cache antigo e descartado junto, o que evita buckets carregando
 * configuracao velha. Nao ha invalidacao manual para dar errado.
 */
final class RateLimitSnapshot {

    /** api-key (header x-itau-api-key) -> configuracao do cliente. */
    private final Map<String, ClientRateLimit> byApiKey;

    /** bucketId -> bucket ja materializado. Preenchido sob demanda. */
    private final ConcurrentHashMap<String, Bucket> buckets;

    /**
     * Versao da configuracao, em epoch millis do momento em que o snapshot foi
     * construido. Usada no {@code withImplicitConfigurationReplacement} do
     * Bucket4j: uma task com configuracao velha (versao menor) nunca sobrescreve
     * no Redis a configuracao nova publicada por outra task.
     */
    private final long version;

    private final BiFunction<String, ClientRateLimit, Bucket> bucketFactory;

    RateLimitSnapshot(Map<String, ClientRateLimit> byApiKey,
                      long version,
                      BiFunction<String, ClientRateLimit, Bucket> bucketFactory) {
        this.byApiKey = Collections.unmodifiableMap(byApiKey);
        this.version = version;
        this.bucketFactory = bucketFactory;
        this.buckets = new ConcurrentHashMap<>(Math.max(16, byApiKey.size() * 2));
    }

    ClientRateLimit configFor(String apiKey) {
        return byApiKey.get(apiKey);
    }

    /**
     * Devolve o bucket do cliente, criando-o na primeira request.
     *
     * <p>O {@code get} antes do {@code computeIfAbsent} nao e microotimizacao
     * gratuita: {@code computeIfAbsent} trava o bin do mapa mesmo quando a chave
     * ja existe, e aqui o caso comum (99,99% das requests) e chave existente.
     */
    Bucket bucketFor(ClientRateLimit config) {
        String bucketId = config.getDynamicKeyRateLimitBucket();
        Bucket cached = buckets.get(bucketId);
        if (cached != null) {
            return cached;
        }
        return buckets.computeIfAbsent(bucketId, id -> bucketFactory.apply(id, config));
    }

    long getVersion() {
        return version;
    }

    int size() {
        return byApiKey.size();
    }
}
