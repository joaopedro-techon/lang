package com.itau.sg2.custodiaposvenda.application.ports.outbound;

import com.itau.sg2.custodiaposvenda.domain.pedido.Pedido;
import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;

import java.util.List;

public interface PublicadorMensagemPort {

    Fluxo fluxoSuportado();

    void publicar(Pedido pedido);

    default void publicar(List<Pedido> pedidos) { pedidos.forEach(this::publicar); }
}
