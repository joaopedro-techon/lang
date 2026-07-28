package com.itau.sg2.custodiaposvenda.application.facade;

import com.itau.sg2.custodiaposvenda.application.ports.inbound.ProcessarPedidoUseCasePort;
import com.itau.sg2.custodiaposvenda.application.ports.outbound.AuditoriaPort;
import com.itau.sg2.custodiaposvenda.application.ports.outbound.ExecutorAssincronoPort;
import com.itau.sg2.custodiaposvenda.application.ports.outbound.IdempotenciaPort;
import com.itau.sg2.custodiaposvenda.application.ports.outbound.MetricasPort;
import com.itau.sg2.custodiaposvenda.application.ports.outbound.PublicadorAuditoriaPort;
import com.itau.sg2.custodiaposvenda.domain.auditoria.EventoAuditoria;
import com.itau.sg2.custodiaposvenda.domain.auditoria.ParametrosAuditoria;
import com.itau.sg2.custodiaposvenda.domain.auditoria.SituacaoAuditoria;
import com.itau.sg2.custodiaposvenda.domain.pedido.PedidoEvent;
import com.itau.sg2.custodiaposvenda.shared.logging.Logger;
import com.itau.sg2.custodiaposvenda.shared.logging.PayloadLog;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

/**
 * Orquestra o processamento de uma mensagem: métrica, auditoria e caso de uso.
 * <p>
 * Depende apenas de portas. Antes importava {@code MetricsConfig}, {@code MdcAwareExecutor} e o
 * {@code Logger} de {@code infrastructure} — a camada de dentro conhecendo a de fora, que é a
 * inversão exata da regra que o hexagonal existe para impor.
 */
@Component
public class ProcessarPedidoFacade {

    private final ProcessarPedidoUseCasePort processarPedidoUseCase;
    private final PublicadorAuditoriaPort publicadorAuditoria;
    private final AuditoriaPort auditoria;
    private final ExecutorAssincronoPort executor;
    private final MetricasPort metricas;
    private final IdempotenciaPort idempotencia;

    public ProcessarPedidoFacade(ProcessarPedidoUseCasePort processarPedidoUseCase,
                                 PublicadorAuditoriaPort publicadorAuditoria,
                                 AuditoriaPort auditoria,
                                 ExecutorAssincronoPort executor,
                                 MetricasPort metricas,
                                 IdempotenciaPort idempotencia) {
        this.processarPedidoUseCase = processarPedidoUseCase;
        this.publicadorAuditoria = publicadorAuditoria;
        this.auditoria = auditoria;
        this.executor = executor;
        this.metricas = metricas;
        this.idempotencia = idempotencia;
    }

    /**
     * A chave inclui o fluxo, e não apenas o {@code idOperacao}: a mesma operação pode
     * legitimamente ser publicada em fluxos diferentes, e usar só o id faria a segunda ser
     * descartada como duplicata.
     */
    private static String chaveIdempotencia(PedidoEvent event) {
        return "pedido#" + event.idOperacao() + "#" + event.fluxo().name();
    }

    public void executar(PedidoEvent event) {
        String fluxo = event.fluxo().name();
        String chave = chaveIdempotencia(event);

        // Fora do timer: uma duplicata descartada não é um processamento, e contá-la distorceria
        // a distribuição de latência.
        if (!idempotencia.tentarIniciar(chave)) {
            metricas.incrementarContador(MetricasPort.PEDIDO_PROCESSADO,
                    MetricasPort.TAG_FLUXO, fluxo,
                    MetricasPort.TAG_STATUS, MetricasPort.STATUS_DUPLICADO);
            return;
        }

        metricas.registrarTempo(MetricasPort.TEMPO_PROCESSAMENTO, () -> {

            try {
                auditoria.iniciar(event.idOperacao());

                auditoria.registrar(() -> new ParametrosAuditoria(SituacaoAuditoria.EVENTO_RECEBIDO));

                processarPedidoUseCase.executar(event);

                // Só depois da publicação ter dado certo. Concluir antes faria uma falha posterior
                // deixar a chave marcada como definitiva, e a reentrega seria descartada.
                idempotencia.concluir(chave);

                auditoria.registrar(() -> new ParametrosAuditoria(SituacaoAuditoria.EVENTO_PROCESSADO_SUCESSO));

                metricas.incrementarContador(MetricasPort.PEDIDO_PROCESSADO,
                        MetricasPort.TAG_FLUXO, fluxo,
                        MetricasPort.TAG_STATUS, MetricasPort.STATUS_SUCESSO);

                Logger.info("Pedido processado com sucesso",
                        PayloadLog.de("idOperacao", event.idOperacao()).e("fluxo", fluxo));
            } catch (Exception ex) {
                // Sem isto, a mensagem some: a reentrega encontraria a chave marcada, seria
                // tratada como duplicata e descartada — sem DLQ, sem erro, sem métrica.
                idempotencia.liberar(chave);

                auditoria.registrar(() -> new ParametrosAuditoria(
                        SituacaoAuditoria.EVENTO_PROCESSADO_ERRO,
                        Map.of("erro", ex.getMessage() != null ? ex.getMessage() : ex.getClass().getSimpleName())
                ));

                metricas.incrementarContador(MetricasPort.PEDIDO_PROCESSADO,
                        MetricasPort.TAG_FLUXO, fluxo,
                        MetricasPort.TAG_STATUS, MetricasPort.STATUS_ERRO);

                Logger.error("Erro ao processar pedido",
                        PayloadLog.de("idOperacao", event.idOperacao()).e("fluxo", fluxo), ex);

                throw ex;
            } finally {
                // Os eventos vivem em ThreadLocal: precisam ser drenados AQUI, na thread que os
                // produziu. Drenar dentro do lambda executaria na virtual thread, onde o
                // ThreadLocal está vazio, e a auditoria seria silenciosamente descartada.
                List<EventoAuditoria> eventos = auditoria.drenar();
                executor.executar(() -> publicadorAuditoria.publicar(eventos));
            }
        }, MetricasPort.TAG_FLUXO, fluxo);
    }
}
