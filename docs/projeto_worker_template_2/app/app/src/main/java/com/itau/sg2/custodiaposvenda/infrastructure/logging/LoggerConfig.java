package com.itau.sg2.custodiaposvenda.infrastructure.logging;

import jakarta.annotation.PostConstruct;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.logging")
public class LoggerConfig {

    private String loggerName;
    private String applicationName;
    private String serviceId;
    private String sigla;
    private String domain;

    @PostConstruct
    void init() { Logger.configure(loggerName, applicationName, serviceId, sigla, domain); }

    public String getLoggerName() { return loggerName; }

    public void setLoggerName(String loggerName) { this.loggerName = loggerName; }

    public String getApplicationName() { return applicationName; }

    public void setApplicationName(String applicationName) { this.applicationName = applicationName; }

    public String getServiceId() { return serviceId; }

    public void setServiceId(String serviceId) { this.serviceId = serviceId; }

    public String getSigla() { return sigla; }

    public void setSigla(String sigla) { this.sigla = sigla; }

    public String getDomain() { return domain; }

    public void setDomain(String domain) { this.domain = domain; }
}
