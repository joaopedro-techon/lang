package com.itau.sg2.custodiaposvenda.infrastructure.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    /** Vai no header das mensagens publicadas — se vier vazio, o consumidor perde a origem. */
    @NotBlank
    private String siglaApp;

    public String getSiglaApp() { return siglaApp; }

    public void setSiglaApp(String siglaApp) { this.siglaApp = siglaApp; }
}
