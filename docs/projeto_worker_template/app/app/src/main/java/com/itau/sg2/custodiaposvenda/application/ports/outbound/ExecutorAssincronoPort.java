package com.itau.sg2.custodiaposvenda.application.ports.outbound;

/**
 * Execução de trabalho fora da thread que atendeu a mensagem.
 * <p>
 * A camada {@code application} precisa dizer "isto não bloqueia o consumo da fila"; ela não
 * precisa saber que existe um pool, virtual threads, propagação de MDC ou semáforo de
 * backpressure. Tudo isso é decisão do adaptador.
 */
public interface ExecutorAssincronoPort {

    /**
     * Submete a tarefa. Pode <b>bloquear</b> o chamador quando o adaptador aplica backpressure —
     * é o comportamento desejado: a ingestão desacelera junto com o consumo.
     */
    void executar(Runnable tarefa);
}
