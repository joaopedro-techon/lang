package com.itau.sg2.custodiaposvenda.domain.pedido;

import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;

import java.util.Arrays;

public record PedidoEvent(Long idOperacao, Fluxo fluxo) {

    public PedidoEvent {
        if (idOperacao == null) {
            throw new IllegalArgumentException("idOperacao não pode ser nulo");
        }
        if (fluxo == null) {
            throw new IllegalArgumentException(
                    "fluxo inválido. Valores permitidos: " + Arrays.toString(Fluxo.values())
            );
        }
    }
}
