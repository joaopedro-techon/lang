package com.itau.sg2.custodiaposvenda.infrastructure.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.executor")
public class ExecutorProperties {

    /**
     * Teto de tarefas assíncronas em voo. Virtual threads são baratas, mas não são de graça: sem
     * teto, um Firehose lento faz as tarefas de auditoria se acumularem indefinidamente enquanto o
     * listener continua consumindo, e o container morre por memória.
     * <p>
     * Ao atingir o teto, quem submete <b>bloqueia</b> — é o backpressure: a ingestão desacelera
     * até a publicação acompanhar.
     */
    private int maxTarefasEmVoo = 100;

    /**
     * Quanto esperar, no shutdown, pelas tarefas já submetidas. Deve ser menor que o
     * {@code stopTimeout} da task ECS, senão o SIGKILL chega antes do dreno terminar.
     */
    private long timeoutEncerramentoSegundos = 20;

    public int getMaxTarefasEmVoo() { return maxTarefasEmVoo; }

    public void setMaxTarefasEmVoo(int maxTarefasEmVoo) { this.maxTarefasEmVoo = maxTarefasEmVoo; }

    public long getTimeoutEncerramentoSegundos() { return timeoutEncerramentoSegundos; }

    public void setTimeoutEncerramentoSegundos(long timeoutEncerramentoSegundos) {
        this.timeoutEncerramentoSegundos = timeoutEncerramentoSegundos;
    }
}
