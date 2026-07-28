package com.itau.sg2.custodiaposvenda.domain.pedido.exception;

/**
 * Falha <b>permanente</b>: reprocessar a mesma mensagem produzirá exatamente o mesmo erro.
 * <p>
 * Mensagens que falham com esta exceção são enviadas diretamente para a DLQ, sem consumir
 * tentativas de reentrega. Falhas transitórias (indisponibilidade de dependências, throttling,
 * timeout) <b>não</b> devem estender esta classe — elas se beneficiam da reentrega via
 * <i>visibility timeout</i> do SQS.
 */
public class PedidoNaoProcessavelException extends RuntimeException {

    public PedidoNaoProcessavelException(String message) {
        super(message);
    }

    public PedidoNaoProcessavelException(String message, Throwable cause) {
        super(message, cause);
    }
}
