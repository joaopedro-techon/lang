package com.itau.sg2.custodiaposvenda.infrastructure.config;

import com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound.MdcAwareExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.Executors;

@Configuration
public class ExecutorConfig {

    /**
     * O {@code ExecutorService} não é exposto como bean próprio de propósito: seriam dois beans
     * com ciclo de vida sobreposto (o Spring fecharia ambos, em ordem não garantida) para um
     * recurso só. Quem é dono do executor é o {@link MdcAwareExecutor}, e é ele que o drena.
     */
    @Bean
    public MdcAwareExecutor mdcAwareExecutor(ExecutorProperties properties) {
        return new MdcAwareExecutor(
                Executors.newVirtualThreadPerTaskExecutor(),
                properties.getMaxTarefasEmVoo(),
                properties.getTimeoutEncerramentoSegundos());
    }
}
