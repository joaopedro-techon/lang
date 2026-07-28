package com.itau.sg2.custodiaposvenda.infrastructure.ratelimit;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Testes com backend LOCAL: exercitam a resolucao de configuracao, o
 * compartilhamento de bucket e o reload. A parte distribuida (Redis + otimizacao
 * preditiva) precisa de Testcontainers e vive em teste separado -- ver README.
 */
class RateLimiterServiceTest {

    private static final String API_KEY_A = "8f0e0b3d-efa1-493f-91c1-34f38704dd4e";
    private static final String API_KEY_B = "1a5fcb56-b19f-445b-b801-ff951f9f412a";
    private static final String BUCKET_COMPARTILHADO = "019dc16f-870a-7c68-a692-4f0ed5e6cc45";

    private static final String CONFIG_JSON = "{"
            + "\"rateLimitConfig\": {"
            + "  \"" + API_KEY_A + "\": {"
            + "    \"dynamicKeyRateLimitBucket\": \"" + BUCKET_COMPARTILHADO + "\","
            + "    \"requestCount\": \"5\", \"requestSeconds\": \"60\""
            + "  },"
            + "  \"" + API_KEY_B + "\": {"
            + "    \"dynamicKeyRateLimitBucket\": \"c7a4f1b2-9e6d-4c3b-b8a1-6e2c9f4d8b62\","
            + "    \"requestCount\": \"2\", \"requestSeconds\": \"60\""
            + "  }"
            + "}}";

    private RateLimitProperties properties;
    private RateLimitRegistry registry;
    private RateLimiterService service;

    @BeforeEach
    void setUp() {
        properties = new RateLimitProperties();
        properties.setBackend(RateLimitProperties.Backend.LOCAL);
        properties.setConfigJson(CONFIG_JSON);
        properties.setConfigVersion(1L);

        registry = new RateLimitRegistry(properties, new BucketFactory(properties, null), new ObjectMapper());
        registry.afterPropertiesSet();

        service = new RateLimiterService(registry, properties, new SimpleMeterRegistry());
    }

    @Test
    @DisplayName("consome a cota do cliente e rejeita a request seguinte")
    void deveRejeitarAposEsgotarCota() {
        for (int i = 0; i < 5; i++) {
            RateLimitDecision decision = service.check(API_KEY_A);
            assertTrue(decision.isAllowed(), "request " + i + " deveria passar");
            assertEquals(5, decision.getLimit());
            assertEquals(4 - i, decision.getRemaining());
        }

        RateLimitDecision excedida = service.check(API_KEY_A);
        assertFalse(excedida.isAllowed());
        assertEquals(0, excedida.getRemaining());
        assertTrue(excedida.getRetryAfterSeconds() >= 1, "Retry-After nunca pode ser 0");
    }

    @Test
    @DisplayName("cotas de clientes distintos sao independentes")
    void cotasNaoSeMisturam() {
        for (int i = 0; i < 5; i++) {
            assertTrue(service.check(API_KEY_A).isAllowed());
        }
        assertFalse(service.check(API_KEY_A).isAllowed());

        // B tem bucket proprio e nao foi afetado por A ter estourado.
        assertTrue(service.check(API_KEY_B).isAllowed());
        assertTrue(service.check(API_KEY_B).isAllowed());
        assertFalse(service.check(API_KEY_B).isAllowed());
    }

    @Test
    @DisplayName("api-keys que apontam para o mesmo dynamicKeyRateLimitBucket dividem a cota")
    void bucketCompartilhadoSomaConsumo() {
        String terceiraKey = "aaaa1111-0000-0000-0000-000000000000";
        properties.setConfigJson("{\"rateLimitConfig\": {"
                + "\"" + API_KEY_A + "\": {\"dynamicKeyRateLimitBucket\": \"" + BUCKET_COMPARTILHADO + "\","
                + " \"requestCount\": \"4\", \"requestSeconds\": \"60\"},"
                + "\"" + terceiraKey + "\": {\"dynamicKeyRateLimitBucket\": \"" + BUCKET_COMPARTILHADO + "\","
                + " \"requestCount\": \"4\", \"requestSeconds\": \"60\"}"
                + "}}");
        properties.setConfigVersion(2L);
        registry.reload();

        assertTrue(service.check(API_KEY_A).isAllowed());
        assertTrue(service.check(terceiraKey).isAllowed());
        assertTrue(service.check(API_KEY_A).isAllowed());
        assertTrue(service.check(terceiraKey).isAllowed());

        // Quatro tokens gastos no total, nao quatro por api-key.
        assertFalse(service.check(API_KEY_A).isAllowed());
        assertFalse(service.check(terceiraKey).isAllowed());
    }

    @Test
    @DisplayName("api-key desconhecida passa direto quando a politica e ALLOW")
    void apiKeyDesconhecidaComAllow() {
        RateLimitDecision decision = service.check("nao-existe-no-config");
        assertTrue(decision.isAllowed());
        assertFalse(decision.hasHeaders(), "sem limite aplicavel, nao deve emitir X-RateLimit-*");
    }

    @Test
    @DisplayName("api-key desconhecida recebe 429 quando a politica e DENY")
    void apiKeyDesconhecidaComDeny() {
        properties.setUnknownKeyPolicy(RateLimitProperties.UnknownKeyPolicy.DENY);
        assertFalse(service.check("nao-existe-no-config").isAllowed());
    }

    @Test
    @DisplayName("header ausente nao quebra o filtro")
    void headerAusente() {
        assertTrue(service.check(null).isAllowed());
    }

    @Test
    @DisplayName("JSON invalido no config server preserva a configuracao anterior")
    void jsonInvalidoNaoDerrubaConfiguracao() {
        properties.setConfigJson("{ isso nao e json }");
        registry.reload();

        // Continua limitando com a configuracao boa que ja estava carregada.
        for (int i = 0; i < 5; i++) {
            assertTrue(service.check(API_KEY_A).isAllowed());
        }
        assertFalse(service.check(API_KEY_A).isAllowed());
    }

    @Test
    @DisplayName("entrada malformada e descartada sem invalidar as demais")
    void entradaInvalidaIsolada() {
        properties.setConfigJson("{\"rateLimitConfig\": {"
                + "\"" + API_KEY_A + "\": {\"dynamicKeyRateLimitBucket\": \"b1\","
                + " \"requestCount\": \"0\", \"requestSeconds\": \"1\"},"
                + "\"" + API_KEY_B + "\": {\"dynamicKeyRateLimitBucket\": \"b2\","
                + " \"requestCount\": \"1\", \"requestSeconds\": \"60\"}"
                + "}}");
        properties.setConfigVersion(3L);
        registry.reload();

        // A tem requestCount=0 (invalido) -> descartado -> cai na politica ALLOW.
        assertTrue(service.check(API_KEY_A).isAllowed());
        assertFalse(service.check(API_KEY_A).hasHeaders());

        // B permanece valido e limitado.
        assertTrue(service.check(API_KEY_B).isAllowed());
        assertFalse(service.check(API_KEY_B).isAllowed());
    }
}
