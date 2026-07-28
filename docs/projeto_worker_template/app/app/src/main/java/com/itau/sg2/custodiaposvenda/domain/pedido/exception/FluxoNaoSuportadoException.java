package com.itau.sg2.custodiaposvenda.domain.pedido.exception;

import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;

/**
 * Não há {@code PublicadorMensagemPort} registrado para o {@link Fluxo} do pedido.
 * <p>
 * É uma falha de configuração/deploy, não transitória: reentregar a mensagem apenas repetiria o
 * erro até esgotar as tentativas.
 */
public class FluxoNaoSuportadoException extends PedidoNaoProcessavelException {

    private final transient Fluxo fluxo;

    public FluxoNaoSuportadoException(Fluxo fluxo) {
        super("Nenhum publicador configurado para o fluxo: " + fluxo);
        this.fluxo = fluxo;
    }

    public Fluxo getFluxo() {
        return fluxo;
    }
}
