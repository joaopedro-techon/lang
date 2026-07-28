package com.itau.sg2.custodiaposvenda.infrastructure.config;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.binder.MeterBinder;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class HttpMetricsConfig {

    private static final String PREFIX = "custom.sg2.dogstatsd.infra.httpclient.pool";

    @Bean
    public MeterBinder httpClientPoolMetrics(PoolingHttpClientConnectionManager connectionManager) {
        return registry -> {

            Gauge.builder(PREFIX + ".max.total", connectionManager, cm -> cm.getTotalStats().getMax())
                    .description("Número máximo de conexões totais no pool")
                    .register(registry);

            Gauge.builder(PREFIX + ".available", connectionManager, cm -> cm.getTotalStats().getAvailable())
                    .description("Número de conexões disponíveis (livres) no pool")
                    .register(registry);

            Gauge.builder(PREFIX + ".leased", connectionManager, cm -> cm.getTotalStats().getLeased())
                    .description("Número de conexões em uso (leased) no pool")
                    .register(registry);

            Gauge.builder(PREFIX + ".pending", connectionManager, cm -> cm.getTotalStats().getPending())
                    .description("Número de requisições pendentes aguardando conexão")
                    .register(registry);

            Gauge.builder(PREFIX + ".utilization.ratio", connectionManager, cm -> {
                        int max = cm.getTotalStats().getMax();
                        return max == 0 ? 0.0 : (double) cm.getTotalStats().getLeased() / max;
                    })
                    .description("Taxa de utilização do pool (0.0 a 1.0)")
                    .register(registry);

            Gauge.builder(PREFIX + ".utilization.percent", connectionManager, cm -> {
                        int max = cm.getTotalStats().getMax();
                        return max == 0 ? 0.0 : ((double) cm.getTotalStats().getLeased() / max) * 100.0;
                    })
                    .description("Taxa de utilização do pool em percentual (0 a 100)")
                    .register(registry);

            Gauge.builder(PREFIX + ".total", connectionManager,
                            cm -> cm.getTotalStats().getAvailable() + cm.getTotalStats().getLeased())
                    .description("Total de conexões no pool (available + leased)")
                    .register(registry);

            Gauge.builder(PREFIX + ".max.per.route", connectionManager, cm -> cm.getDefaultMaxPerRoute())
                    .description("Número máximo de conexões por rota (por host)")
                    .register(registry);
        };
    }
}
