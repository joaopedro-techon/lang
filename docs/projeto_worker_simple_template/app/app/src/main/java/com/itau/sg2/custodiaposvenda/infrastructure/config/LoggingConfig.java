package com.itau.sg2.custodiaposvenda.infrastructure.config;

import com.itau.sg2.custodiaposvenda.shared.logging.Logger;
import jakarta.annotation.PostConstruct;
import org.springframework.context.annotation.Configuration;

/**
 * Aplica {@link LoggingProperties} ao {@link Logger}.
 * <p>
 * Existe separado das properties para que o efeito colateral fique num lugar chamado
 * "configuração", e não escondido no ciclo de vida de um objeto de dados.
 */
@Configuration
public class LoggingConfig {

    private final LoggingProperties properties;

    public LoggingConfig(LoggingProperties properties) { this.properties = properties; }

    @PostConstruct
    void configurarLogger() {
        Logger.configure(
                properties.getLoggerName(),
                properties.getApplicationName(),
                properties.getServiceId(),
                properties.getSigla(),
                properties.getDomain());
    }
}
