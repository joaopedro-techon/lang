package com.itau.sg2.custodiaposvenda.application.ports.inbound;

import com.itau.sg2.custodiaposvenda.domain.pedido.PedidoEvent;

/**
 * Porta de entrada: o que a aplicação sabe fazer quando um pedido chega pela fila.
 * <p>
 * O adaptador de entrada (o listener do SQS) depende desta interface, não da implementação —
 * é o que permite exercitar o caso de uso sem SQS e trocar a origem da mensagem sem tocá-lo.
 */
public interface ProcessarPedidoUseCasePort {

    void executar(PedidoEvent event);
}
