package com.itau.sg2.custodiaposvenda.infrastructure.config;

import feign.Client;
import feign.hc5.ApacheHttp5Client;
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Cliente HTTP do Feign.
 * <p>
 * As propriedades chegam por parâmetro de método, vindas de {@link FeignHttpProperties}, e não por
 * {@code @Value} em campo. Injeção em campo numa {@code @Configuration} deixa o objeto num estado
 * meio-construído durante a criação dos beans e não é testável sem contexto Spring.
 */
@Configuration
public class FeignConfig {

    /**
     * {@code setConnectionTimeToLive} no builder está deprecado no HttpClient 5.4: o TTL migrou
     * para {@link ConnectionConfig}, junto com os demais parâmetros de conexão.
     */
    @Bean
    public PoolingHttpClientConnectionManager connectionManager(FeignHttpProperties properties) {
        var connectionManager = PoolingHttpClientConnectionManagerBuilder.create()
                .setDefaultConnectionConfig(ConnectionConfig.custom()
                        .setTimeToLive(TimeValue.ofSeconds(properties.getTimeToLive()))
                        .build())
                .build();
        connectionManager.setMaxTotal(properties.getMaxConnections());
        connectionManager.setDefaultMaxPerRoute(properties.getMaxConnectionsPerRoute());
        return connectionManager;
    }

    @Bean
    public CloseableHttpClient httpClient(PoolingHttpClientConnectionManager connectionManager,
                                          FeignHttpProperties properties) {
        RequestConfig requestConfig = RequestConfig.custom()
                .setConnectionRequestTimeout(Timeout.ofMilliseconds(properties.getConnectionRequestTimeout()))
                .build();

        return HttpClients.custom()
                .setConnectionManager(connectionManager)
                .setDefaultRequestConfig(requestConfig)
                .build();
    }

    @Bean
    public Client feignClient(CloseableHttpClient httpClient) { return new ApacheHttp5Client(httpClient); }
}
