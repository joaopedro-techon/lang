package com.itau.sg2.custodiaposvenda.domain.pedido;

import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;
import com.itau.sg2.custodiaposvenda.domain.pedido.exception.PedidoInvalidoException;

import java.util.Arrays;

/**
 * Evento de entrada da fila de pedidos.
 * <p>
 * A validação é <b>explícita</b> ({@link #validar()}) e não feita no construtor canônico de
 * propósito: se o construtor lançasse, a falha ocorreria dentro da desserialização do Jackson,
 * antes de o listener ser invocado. Sem acesso ao {@code Acknowledgement}, a mensagem nunca seria
 * confirmada nem roteada para a DLQ — resultando em reprocessamento infinito de uma mensagem que
 * jamais terá sucesso.
 */
public record PedidoEvent(Long idOperacao, Fluxo fluxo) {

    /**
     * @throws PedidoInvalidoException se o evento não puder ser processado (falha permanente)
     */
    public void validar() {
        if (idOperacao == null) {
            throw new PedidoInvalidoException("idOperacao não pode ser nulo");
        }
        if (fluxo == null) {
            throw new PedidoInvalidoException(
                    "fluxo inválido ou ausente. Valores permitidos: " + Arrays.toString(Fluxo.values())
            );
        }
    }
}
