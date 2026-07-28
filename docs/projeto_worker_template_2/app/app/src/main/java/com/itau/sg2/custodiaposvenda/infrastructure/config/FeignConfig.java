package com.itau.sg2.custodiaposvenda.infrastructure.config;

import feign.Client;
import feign.hc5.ApacheHttp5Client;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FeignConfig {

    @Value("${spring.cloud.openfeign.httpclient.max-connections}")
    private int maxConnections;

    @Value("${spring.cloud.openfeign.httpclient.max-connections-per-route}")
    private int maxConnectionsPerRoute;

    @Value("${spring.cloud.openfeign.httpclient.connection-request-timeout}")
    private int connectionRequestTimeout;

    @Value("${spring.cloud.openfeign.httpclient.time-to-live}")
    private int timeToLiveSeconds;

    @Bean
    public PoolingHttpClientConnectionManager connectionManager() {
        var connectionManager = PoolingHttpClientConnectionManagerBuilder.create()
                .setConnectionTimeToLive(TimeValue.ofSeconds(timeToLiveSeconds))
                .build();
        connectionManager.setMaxTotal(maxConnections);
        connectionManager.setDefaultMaxPerRoute(maxConnectionsPerRoute);
        return connectionManager;
    }

    @Bean
    public CloseableHttpClient httpClient(PoolingHttpClientConnectionManager connectionManager) {
        RequestConfig requestConfig = RequestConfig.custom()
                .setConnectionRequestTimeout(Timeout.ofMilliseconds(connectionRequestTimeout))
                .build();

        return HttpClients.custom()
                .setConnectionManager(connectionManager)
                .setDefaultRequestConfig(requestConfig)
                .build();
    }

    @Bean
    public Client feignClient(CloseableHttpClient httpClient) { return new ApacheHttp5Client(httpClient); }
}
