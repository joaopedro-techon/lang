package com.itau.sg2.custodiaposvenda.application.facade;

import com.itau.sg2.custodiaposvenda.application.ports.inbound.ProcessarPedidoUseCasePort;
import com.itau.sg2.custodiaposvenda.application.ports.outbound.MetricasPort;
import com.itau.sg2.custodiaposvenda.domain.pedido.PedidoEvent;
import com.itau.sg2.custodiaposvenda.shared.logging.Logger;
import com.itau.sg2.custodiaposvenda.shared.logging.PayloadLog;
import org.springframework.stereotype.Component;

/**
 * Envelopa o caso de uso com o que é transversal a qualquer processamento: tempo, contador de
 * desfecho e log de conclusão.
 * <p>
 * Existe separada de {@code ProcessarPedidoService} para que as duas tenham um motivo de mudança
 * cada: a fachada muda quando muda o que se observa, o caso de uso quando muda o que se faz.
 * Misturadas, todo teste do fluxo precisaria de um dublê de métrica, e o try/catch da observação se
 * confundiria com o tratamento de erro do negócio.
 * <p>
 * Depende apenas de portas — {@link ProcessarPedidoUseCasePort} e {@link MetricasPort} —, nunca de
 * {@code infrastructure}. O {@code Logger} vive em {@code shared} justamente para poder ser usado
 * aqui sem inverter a regra de dependência (ADR-0003).
 * <p>
 * <b>A exceção é relançada.</b> Observar a falha não é tratá-la: quem decide o destino da mensagem é
 * o listener, que só confirma no caminho de sucesso, e engolir a exceção aqui faria toda falha ser
 * confirmada como sucesso — mensagem perdida, sem DLQ (ADR-0001).
 */
@Component
public class ProcessarPedidoFacade {

    private final ProcessarPedidoUseCasePort processarPedidoUseCase;
    private final MetricasPort metricas;

    public ProcessarPedidoFacade(ProcessarPedidoUseCasePort processarPedidoUseCase, MetricasPort metricas) {
        this.processarPedidoUseCase = processarPedidoUseCase;
        this.metricas = metricas;
    }

    public void executar(PedidoEvent event) {
        String fluxo = event.fluxo().name();

        metricas.registrarTempo(MetricasPort.TEMPO_PROCESSAMENTO, () -> {
            try {
                processarPedidoUseCase.executar(event);

                metricas.incrementarContador(MetricasPort.PEDIDO_PROCESSADO,
                        MetricasPort.TAG_FLUXO, fluxo,
                        MetricasPort.TAG_STATUS, MetricasPort.STATUS_SUCESSO);

                Logger.info("Pedido processado com sucesso", contexto(event));
            } catch (RuntimeException ex) {
                metricas.incrementarContador(MetricasPort.PEDIDO_PROCESSADO,
                        MetricasPort.TAG_FLUXO, fluxo,
                        MetricasPort.TAG_STATUS, MetricasPort.STATUS_ERRO);

                Logger.error("Erro ao processar pedido", contexto(event), ex);

                throw ex;
            }
        }, MetricasPort.TAG_FLUXO, fluxo);
    }

    private static PayloadLog contexto(PedidoEvent event) {
        return PayloadLog.de("idCliente", event.idCliente())
                .e("idPedido", event.idPedido())
                .e("fluxo", event.fluxo());
    }
}
