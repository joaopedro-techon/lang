package com.itau.sg2.custodiaposvenda.infrastructure.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.itau.sg2.custodiaposvenda.domain.auditoria.AuditoriaContext;
import jakarta.annotation.PostConstruct;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AuditoriaConfig {

    private final ObjectMapper objectMapper;

    public AuditoriaConfig(ObjectMapper objectMapper) { this.objectMapper = objectMapper; }

    @PostConstruct
    void init() { AuditoriaContext.configurarObjectMapper(objectMapper); }
}
