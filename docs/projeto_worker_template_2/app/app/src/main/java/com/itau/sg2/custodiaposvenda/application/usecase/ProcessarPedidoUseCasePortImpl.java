package com.itau.sg2.custodiaposvenda.application.usecase;

import com.itau.sg2.custodiaposvenda.application.ports.inbound.ProcessarPedidoUseCasePort;
import com.itau.sg2.custodiaposvenda.application.ports.outbound.PublicadorMensagemPort;
import com.itau.sg2.custodiaposvenda.domain.pedido.Pedido;
import com.itau.sg2.custodiaposvenda.domain.pedido.PedidoEvent;
import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;
import com.itau.sg2.custodiaposvenda.infrastructure.logging.Logger;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class ProcessarPedidoUseCasePortImpl implements ProcessarPedidoUseCasePort {

    private final Map<Fluxo, PublicadorMensagemPort> publicadores;

    public ProcessarPedidoUseCasePortImpl(List<PublicadorMensagemPort> publicadores) {
        this.publicadores = publicadores.stream()
                .collect(Collectors.toMap(PublicadorMensagemPort::fluxoSuportado, Function.identity()));
    }

    @Override
    public void executar(PedidoEvent event) {
        Pedido pedido = Pedido.from(event);

        PublicadorMensagemPort publicador = publicadores.get(pedido.getFluxo());

        if (publicador == null) {
            throw new IllegalStateException("Nenhum publicador configurado para o fluxo: " + pedido.getFluxo());
        }

        Logger.info("Processando pedido", pedido);

        publicador.publicar(pedido);
        pedido.marcarComoProcessado();

        Logger.info("Pedido processado com sucesso", pedido);
    }
}
