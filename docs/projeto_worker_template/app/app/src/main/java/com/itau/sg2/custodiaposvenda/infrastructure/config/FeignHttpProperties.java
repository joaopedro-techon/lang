package com.itau.sg2.custodiaposvenda.infrastructure.config;

import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * Pool HTTP do Feign.
 * <p>
 * Reflete {@code spring.cloud.openfeign.httpclient.*} porque o {@link FeignConfig} monta o
 * {@code PoolingHttpClientConnectionManager} à mão e precisa dos mesmos valores.
 */
@Validated
@ConfigurationProperties(prefix = "spring.cloud.openfeign.httpclient")
public class FeignHttpProperties {

    @Min(1)
    private int maxConnections = 200;

    @Min(1)
    private int maxConnectionsPerRoute = 50;

    /** Milissegundos de espera por uma conexão do pool. */
    @Min(1)
    private int connectionRequestTimeout = 3000;

    /** Segundos de vida de uma conexão ociosa no pool. */
    @Min(1)
    private int timeToLive = 30;

    public int getMaxConnections() { return maxConnections; }

    public void setMaxConnections(int maxConnections) { this.maxConnections = maxConnections; }

    public int getMaxConnectionsPerRoute() { return maxConnectionsPerRoute; }

    public void setMaxConnectionsPerRoute(int maxConnectionsPerRoute) {
        this.maxConnectionsPerRoute = maxConnectionsPerRoute;
    }

    public int getConnectionRequestTimeout() { return connectionRequestTimeout; }

    public void setConnectionRequestTimeout(int connectionRequestTimeout) {
        this.connectionRequestTimeout = connectionRequestTimeout;
    }

    public int getTimeToLive() { return timeToLive; }

    public void setTimeToLive(int timeToLive) { this.timeToLive = timeToLive; }
}
