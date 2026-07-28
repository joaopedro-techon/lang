package com.itau.sg2.custodiaposvenda.infrastructure.config;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.util.StringJoiner;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

@Component
public class MetricsConfig {

    public static final String METRIC_TEMPO_PROCESSAMENTO = "custom.sg2.dogstatsd.app.pedido.processamento.duration";
    public static final String METRIC_PEDIDO_PROCESSADO = "custom.sg2.dogstatsd.app.pedido.count";

    public static final String TAG_FLUXO = "fluxo";
    public static final String TAG_STATUS = "status";

    public static final String STATUS_SUCESSO = "sucesso";
    public static final String STATUS_ERRO = "erro";

    private final MeterRegistry meterRegistry;
    private final ConcurrentMap<String, Counter> counters = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, Timer> timers = new ConcurrentHashMap<>();

    public MetricsConfig(MeterRegistry meterRegistry) { this.meterRegistry = meterRegistry; }

    public void incrementCounter(String name, String... tags) {
        var key = buildCacheKey(name, tags);
        counters.computeIfAbsent(key, _ -> Counter.builder(name).tags(tags).register(meterRegistry))
                .increment();
    }

    public Timer getTimer(String name, String... tags) {
        var key = buildCacheKey(name, tags);
        return timers.computeIfAbsent(key, _ -> Timer.builder(name).tags(tags).register(meterRegistry));
    }

    private String buildCacheKey(String name, String... tags) {
        var joiner = new StringJoiner("|");
        joiner.add(name);
        for (String tag : tags) {
            joiner.add(tag);
        }
        return joiner.toString();
    }
}
