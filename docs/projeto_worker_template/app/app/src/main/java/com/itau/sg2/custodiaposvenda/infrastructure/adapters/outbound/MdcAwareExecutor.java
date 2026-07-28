package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import com.itau.sg2.custodiaposvenda.application.ports.outbound.ExecutorAssincronoPort;
import com.itau.sg2.custodiaposvenda.shared.logging.Logger;
import com.itau.sg2.custodiaposvenda.shared.logging.PayloadLog;
import org.slf4j.MDC;

import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

/**
 * Adaptador de {@link ExecutorAssincronoPort}: propaga o MDC, aplica backpressure e drena no
 * shutdown.
 * <p>
 * <b>Backpressure.</b> O executor de virtual threads é ilimitado por natureza. Quem publica a
 * auditoria não espera o resultado, então uma dependência lenta faz as tarefas se acumularem sem
 * limite enquanto o listener continua consumindo da fila. O semáforo põe um teto: ao atingi-lo,
 * {@link #executar(Runnable)} bloqueia o chamador e a ingestão desacelera junto.
 * <p>
 * <b>Shutdown.</b> Sem dreno, todo release descartava as tarefas em voo — perda de auditoria a
 * cada deploy. {@link #close()} para de aceitar novas tarefas e espera as submetidas por um tempo
 * limitado.
 */
public class MdcAwareExecutor implements ExecutorAssincronoPort, AutoCloseable {

    private final ExecutorService delegate;
    private final Semaphore vagas;
    private final long timeoutEncerramentoSegundos;

    public MdcAwareExecutor(ExecutorService delegate, int maxTarefasEmVoo, long timeoutEncerramentoSegundos) {
        this.delegate = delegate;
        this.vagas = new Semaphore(maxTarefasEmVoo);
        this.timeoutEncerramentoSegundos = timeoutEncerramentoSegundos;
    }

    @Override
    public void executar(Runnable tarefa) {
        Map<String, String> contextMap = MDC.getCopyOfContextMap();

        // Bloqueia aqui quando o teto é atingido — este é o ponto de backpressure.
        vagas.acquireUninterruptibly();

        try {
            delegate.execute(() -> {
                if (contextMap != null) {
                    MDC.setContextMap(contextMap);
                }
                try {
                    tarefa.run();
                } catch (RuntimeException ex) {
                    // Tarefa fire-and-forget: sem este catch a exceção só chegaria ao
                    // UncaughtExceptionHandler da thread, fora do log estruturado.
                    Logger.error("Falha em tarefa assíncrona.", ex);
                } finally {
                    // clear() e não um restore do mapa anterior: cada tarefa roda numa virtual
                    // thread nova, criada por este executor. Não há contexto de terceiros para
                    // preservar — e o delegate não é compartilhado com ninguém.
                    MDC.clear();
                    vagas.release();
                }
            });
        } catch (RejectedExecutionException ex) {
            // O executor já foi encerrado (shutdown em andamento). A vaga precisa voltar aqui:
            // o bloco finally acima nunca vai rodar porque a tarefa não chegou a ser aceita.
            vagas.release();
            Logger.error("Tarefa assíncrona rejeitada: executor já encerrado.", ex);
        }
    }

    /**
     * Chamado pelo Spring no fechamento do contexto ({@code destroyMethod} inferido).
     * <p>
     * O container do listener SQS é um {@code SmartLifecycle} e é parado <b>antes</b> da destruição
     * dos beans, então quando este método roda já não entram tarefas novas — resta esperar as que
     * estão em voo.
     */
    @Override
    public void close() {
        delegate.shutdown();
        try {
            if (!delegate.awaitTermination(timeoutEncerramentoSegundos, TimeUnit.SECONDS)) {
                Logger.warn("Tarefas assíncronas não terminaram no tempo limite; encerrando à força.",
                        PayloadLog.de("timeoutSegundos", timeoutEncerramentoSegundos));
                delegate.shutdownNow();
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            delegate.shutdownNow();
        }
    }
}
