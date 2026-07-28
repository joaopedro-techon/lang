package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import com.itau.sg2.custodiaposvenda.application.ports.outbound.MetricasPort;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.util.StringJoiner;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

/**
 * Adaptador de {@link MetricasPort} sobre o Micrometer.
 * <p>
 * Era {@code infrastructure.config.MetricsConfig} — nome e pacote enganosos: não é
 * {@code @Configuration}, não declara bean nenhum e não configura nada. É um adaptador de saída,
 * com estado (o cache de medidores), e agora está no pacote que corresponde ao que ele é.
 * <p>
 * O cache existe porque {@code Counter.builder(...).register(...)} percorre os medidores já
 * registrados a cada chamada — caro no caminho quente.
 */
@Component
public class MicrometerMetricasAdapter implements MetricasPort {

    private final MeterRegistry meterRegistry;
    private final ConcurrentMap<String, Counter> counters = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, Timer> timers = new ConcurrentHashMap<>();

    public MicrometerMetricasAdapter(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Override
    public void incrementarContador(String nome, String... tags) {
        counters.computeIfAbsent(chaveCache(nome, tags),
                        _ -> Counter.builder(nome).tags(tags).register(meterRegistry))
                .increment();
    }

    @Override
    public void registrarTempo(String nome, Runnable acao, String... tags) {
        timers.computeIfAbsent(chaveCache(nome, tags),
                        _ -> Timer.builder(nome).tags(tags).register(meterRegistry))
                .record(acao);
    }

    private String chaveCache(String nome, String... tags) {
        var joiner = new StringJoiner("|");
        joiner.add(nome);
        for (String tag : tags) {
            joiner.add(tag);
        }
        return joiner.toString();
    }
}
