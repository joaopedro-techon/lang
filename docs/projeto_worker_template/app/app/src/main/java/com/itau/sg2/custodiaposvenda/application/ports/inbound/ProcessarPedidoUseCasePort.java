package com.itau.sg2.custodiaposvenda.application.ports.inbound;

import com.itau.sg2.custodiaposvenda.domain.pedido.PedidoEvent;

public interface ProcessarPedidoUseCasePort {

    void executar(PedidoEvent event);
}
