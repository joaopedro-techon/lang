package com.itau.sg2.custodiaposvenda.infrastructure.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private String siglaApp;

    public String getSiglaApp() { return siglaApp; }

    public void setSiglaApp(String siglaApp) { this.siglaApp = siglaApp; }
}
