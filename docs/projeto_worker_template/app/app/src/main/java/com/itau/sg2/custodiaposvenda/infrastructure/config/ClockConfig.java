package com.itau.sg2.custodiaposvenda.infrastructure.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Clock;

/**
 * Fonte de tempo da aplicação.
 * <p>
 * Existe para que nenhum ponto do domínio chame {@code Instant.now()} direto. Sem um relógio
 * injetável, qualquer asserção sobre um timestamp — no payload publicado ou no evento de
 * auditoria — vira teste que depende do relógio da máquina, e portanto não é escrito.
 * <p>
 * UTC explícito: o fuso do container é {@code America/Sao_Paulo} (definido no Dockerfile), e
 * timestamps que cruzam a fronteira do processo devem ser absolutos.
 */
@Configuration
public class ClockConfig {

    @Bean
    public Clock clock() { return Clock.systemUTC(); }
}
