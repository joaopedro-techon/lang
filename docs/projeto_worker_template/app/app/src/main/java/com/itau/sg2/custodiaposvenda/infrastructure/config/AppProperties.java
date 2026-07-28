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

    private final Auditoria auditoria = new Auditoria();

    public String getSiglaApp() { return siglaApp; }

    public void setSiglaApp(String siglaApp) { this.siglaApp = siglaApp; }

    public Auditoria getAuditoria() { return auditoria; }

    /** Aninhada para casar com {@code app.auditoria.ativa} do yml. */
    public static class Auditoria {

        /** Desligada, nenhum evento é acumulado nem publicado. */
        private boolean ativa = true;

        public boolean isAtiva() { return ativa; }

        public void setAtiva(boolean ativa) { this.ativa = ativa; }
    }
}
