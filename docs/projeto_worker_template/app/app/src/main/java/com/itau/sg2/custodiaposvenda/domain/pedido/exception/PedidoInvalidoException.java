package com.itau.sg2.custodiaposvenda.domain.pedido.exception;

/**
 * O evento recebido não satisfaz as invariantes de {@code PedidoEvent} (campo obrigatório ausente,
 * valor fora do domínio). Nenhuma quantidade de reentregas corrige o conteúdo da mensagem.
 */
public class PedidoInvalidoException extends PedidoNaoProcessavelException {

    public PedidoInvalidoException(String message) {
        super(message);
    }
}
