package com.itau.sg2.custodiaposvenda.application.usecase;

import com.itau.sg2.custodiaposvenda.application.ports.inbound.ProcessarPedidoUseCasePort;
import com.itau.sg2.custodiaposvenda.application.ports.outbound.PublicadorPedidoPort;
import com.itau.sg2.custodiaposvenda.domain.pedido.Pedido;
import com.itau.sg2.custodiaposvenda.domain.pedido.PedidoEvent;
import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;
import com.itau.sg2.custodiaposvenda.domain.pedido.exception.FluxoNaoSuportadoException;
import com.itau.sg2.custodiaposvenda.shared.logging.Logger;
import com.itau.sg2.custodiaposvenda.shared.logging.PayloadLog;
import org.springframework.stereotype.Service;

import java.time.Clock;
import java.util.Arrays;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * O fluxo, em dois passos: monta o pedido a partir do evento e publica no destino do seu fluxo.
 * <p>
 * Esta classe é o lugar onde a ordem das operações está escrita, e é só isso que ela faz. Não sabe o
 * que é SNS, SQS ou Firehose — fala com {@link PublicadorPedidoPort} — e não sabe de métrica nem de
 * log de desfecho, que ficam na fachada. Um caso de uso que só orquestra pode ser lido inteiro de
 * uma vez e testado com dublês.
 */
@Service
public class ProcessarPedidoService implements ProcessarPedidoUseCasePort {

    private final Map<Fluxo, PublicadorPedidoPort> publicadores;
    private final Clock clock;

    public ProcessarPedidoService(List<PublicadorPedidoPort> publicadores, Clock clock) {
        this.publicadores = indexarPorFluxo(publicadores);
        this.clock = clock;
        alertarFluxosSemPublicador();
    }

    @Override
    public void executar(PedidoEvent event) {
        PublicadorPedidoPort publicador = publicadorDe(event.fluxo());

        publicador.publicar(Pedido.de(event, clock.instant()));
    }

    private PublicadorPedidoPort publicadorDe(Fluxo fluxo) {
        PublicadorPedidoPort publicador = publicadores.get(fluxo);

        if (publicador == null) {
            throw new FluxoNaoSuportadoException(fluxo);
        }

        return publicador;
    }

    private static Map<Fluxo, PublicadorPedidoPort> indexarPorFluxo(List<PublicadorPedidoPort> publicadores) {
        return publicadores.stream().collect(Collectors.toMap(
                PublicadorPedidoPort::fluxoSuportado,
                publicador -> publicador,
                (a, b) -> {
                    throw new IllegalStateException(
                            "Há mais de um PublicadorPedidoPort para o fluxo " + a.fluxoSuportado()
                                    + ": " + a.getClass().getName() + " e " + b.getClass().getName()
                                    + ". Cada fluxo deve ter exatamente um publicador.");
                },
                () -> new EnumMap<>(Fluxo.class)));
    }

    /**
     * Um fluxo declarado no enum sem publicador correspondente só falha quando a primeira mensagem
     * daquele tipo chega — em produção. O aviso no startup antecipa o diagnóstico.
     */
    private void alertarFluxosSemPublicador() {
        List<Fluxo> semPublicador = Arrays.stream(Fluxo.values())
                .filter(fluxo -> !publicadores.containsKey(fluxo))
                .toList();

        if (!semPublicador.isEmpty()) {
            Logger.warn("Fluxos declarados sem PublicadorPedidoPort registrado",
                    PayloadLog.de("fluxos", semPublicador.toString()));
        }
    }
}
