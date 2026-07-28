package com.itau.sg2.custodiaposvenda.application.facade;

import com.itau.sg2.custodiaposvenda.application.ports.inbound.ProcessarPedidoUseCasePort;
import com.itau.sg2.custodiaposvenda.application.ports.outbound.PublicadorAuditoriaPort;
import com.itau.sg2.custodiaposvenda.domain.auditoria.AuditoriaContext;
import com.itau.sg2.custodiaposvenda.domain.auditoria.AuditoriaContext.ParametrosAuditoria;
import com.itau.sg2.custodiaposvenda.domain.auditoria.SituacaoAuditoria;
import com.itau.sg2.custodiaposvenda.domain.pedido.PedidoEvent;
import com.itau.sg2.custodiaposvenda.infrastructure.config.MdcAwareExecutor;
import com.itau.sg2.custodiaposvenda.infrastructure.config.MetricsConfig;
import com.itau.sg2.custodiaposvenda.infrastructure.logging.Logger;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.Map;

import static com.itau.sg2.custodiaposvenda.infrastructure.config.MetricsConfig.METRIC_PEDIDO_PROCESSADO;
import static com.itau.sg2.custodiaposvenda.infrastructure.config.MetricsConfig.METRIC_TEMPO_PROCESSAMENTO;
import static com.itau.sg2.custodiaposvenda.infrastructure.config.MetricsConfig.STATUS_ERRO;
import static com.itau.sg2.custodiaposvenda.infrastructure.config.MetricsConfig.STATUS_SUCESSO;
import static com.itau.sg2.custodiaposvenda.infrastructure.config.MetricsConfig.TAG_FLUXO;
import static com.itau.sg2.custodiaposvenda.infrastructure.config.MetricsConfig.TAG_STATUS;

@Component
public class ProcessarPedidoFacade {

    private final ProcessarPedidoUseCasePort processarPedidoUseCase;
    private final PublicadorAuditoriaPort publicadorAuditoria;
    private final MdcAwareExecutor mdcAwareExecutor;
    private final MetricsConfig metrics;
    private final boolean auditoriaAtiva;

    public ProcessarPedidoFacade(ProcessarPedidoUseCasePort processarPedidoUseCase,
                                 PublicadorAuditoriaPort publicadorAuditoria,
                                 MdcAwareExecutor mdcAwareExecutor,
                                 MetricsConfig metrics,
                                 @Value("${app.auditoria.ativa:true}") boolean auditoriaAtiva) {
        this.processarPedidoUseCase = processarPedidoUseCase;
        this.publicadorAuditoria = publicadorAuditoria;
        this.mdcAwareExecutor = mdcAwareExecutor;
        this.metrics = metrics;
        this.auditoriaAtiva = auditoriaAtiva;
    }

    public void executar(PedidoEvent event) {
        metrics.getTimer(METRIC_TEMPO_PROCESSAMENTO, TAG_FLUXO, event.fluxo().name()).record(() -> {

            try {
                AuditoriaContext.iniciar(auditoriaAtiva, event.idOperacao());

                AuditoriaContext.registrar(() -> new ParametrosAuditoria(SituacaoAuditoria.EVENTO_RECEBIDO));

                processarPedidoUseCase.executar(event);

                AuditoriaContext.registrar(() -> new ParametrosAuditoria(SituacaoAuditoria.EVENTO_PROCESSADO_SUCESSO));

                metrics.incrementCounter(METRIC_PEDIDO_PROCESSADO, TAG_FLUXO, event.fluxo().name(), TAG_STATUS, STATUS_SUCESSO);

                Logger.info("Pedido processado com sucesso. fluxo=" + event.fluxo().name());
            } catch (Exception ex) {
                AuditoriaContext.registrar(() -> new ParametrosAuditoria(
                        SituacaoAuditoria.EVENTO_PROCESSADO_ERRO,
                        Map.of("erro", ex.getMessage() != null ? ex.getMessage() : ex.getClass().getSimpleName())
                ));

                metrics.incrementCounter(METRIC_PEDIDO_PROCESSADO, TAG_FLUXO, event.fluxo().name(), TAG_STATUS, STATUS_ERRO);

                Logger.error("Erro ao processar pedido. fluxo=" + event.fluxo().name(), event, ex);

                throw ex;
            } finally {
                mdcAwareExecutor.execute(() -> publicadorAuditoria.publicar(AuditoriaContext.obterEventos()));
                AuditoriaContext.limpar();
            }
        });
    }
}
