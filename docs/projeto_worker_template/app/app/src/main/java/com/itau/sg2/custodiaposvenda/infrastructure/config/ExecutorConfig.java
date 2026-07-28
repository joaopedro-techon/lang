package com.itau.sg2.custodiaposvenda.infrastructure.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@Configuration
public class ExecutorConfig {

    @Bean
    public ExecutorService virtualThreadExecutor() { return Executors.newVirtualThreadPerTaskExecutor(); }

    @Bean
    public MdcAwareExecutor mdcAwareExecutor(ExecutorService virtualThreadExecutor) {
        return new MdcAwareExecutor(virtualThreadExecutor);
    }
}
