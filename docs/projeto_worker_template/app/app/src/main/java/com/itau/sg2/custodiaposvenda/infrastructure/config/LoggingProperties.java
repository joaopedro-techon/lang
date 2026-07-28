package com.itau.sg2.custodiaposvenda.infrastructure.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Identificação da aplicação nos campos fixos do log.
 * <p>
 * Só carrega valores. A versão anterior era um {@code @ConfigurationProperties} que disparava
 * {@code Logger.configure(...)} no próprio {@code @PostConstruct} — um objeto de configuração
 * causando efeito colateral global no momento em que era populado. Quem lesse a classe procurando
 * "que propriedades existem" não esperava encontrar ali a inicialização do log. O efeito agora
 * está em {@link LoggingConfig}.
 */
@ConfigurationProperties(prefix = "app.logging")
public class LoggingProperties {

    private String loggerName;
    private String applicationName;
    private String serviceId;
    private String sigla;
    private String domain;

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
