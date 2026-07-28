package com.itau.sg2.custodiaposvenda.application.usecase;

import com.itau.sg2.custodiaposvenda.application.ports.inbound.ProcessarPedidoUseCasePort;
import com.itau.sg2.custodiaposvenda.application.ports.outbound.PublicadorMensagemPort;
import com.itau.sg2.custodiaposvenda.domain.pedido.Pedido;
import com.itau.sg2.custodiaposvenda.domain.pedido.PedidoEvent;
import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;
import com.itau.sg2.custodiaposvenda.domain.pedido.exception.FluxoNaoSuportadoException;
import com.itau.sg2.custodiaposvenda.shared.logging.Logger;
import org.springframework.stereotype.Service;

import java.time.Clock;
import java.util.Arrays;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Roteia o pedido para o publicador do seu fluxo.
 * <p>
 * Era {@code ProcessarPedidoUseCasePortImpl}: o sufixo descrevia a relação com a interface, não o
 * que a classe faz — e "Impl" é o que se escreve quando não se decidiu o nome.
 */
@Service
public class ProcessarPedidoService implements ProcessarPedidoUseCasePort {

    private final Map<Fluxo, PublicadorMensagemPort> publicadores;
    private final Clock clock;

    public ProcessarPedidoService(List<PublicadorMensagemPort> publicadores, Clock clock) {
        this.publicadores = indexarPorFluxo(publicadores);
        this.clock = clock;
        alertarFluxosSemPublicador();
    }

    @Override
    public void executar(PedidoEvent event) {
        PublicadorMensagemPort publicador = publicadores.get(event.fluxo());

        if (publicador == null) {
            throw new FluxoNaoSuportadoException(event.fluxo());
        }

        // Não há log de sucesso aqui: o listener já registra o recebimento e a fachada registra o
        // desfecho. Um terceiro log por mensagem só multiplica volume no caminho quente.
        publicador.publicar(Pedido.de(event, clock.instant()));
    }

    private static Map<Fluxo, PublicadorMensagemPort> indexarPorFluxo(List<PublicadorMensagemPort> publicadores) {
        return publicadores.stream().collect(Collectors.toMap(
                PublicadorMensagemPort::fluxoSuportado,
                publicador -> publicador,
                (a, b) -> {
                    throw new IllegalStateException(
                            "Há mais de um PublicadorMensagemPort para o fluxo " + a.fluxoSuportado()
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
            Logger.warn("Fluxos declarados sem PublicadorMensagemPort registrado: " + semPublicador
                    + ". Mensagens com esses fluxos irão para a DLQ.");
        }
    }
}
