package com.itau.sg2.custodiaposvenda.domain.pedido;

import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;
import com.itau.sg2.custodiaposvenda.domain.pedido.exception.PedidoInvalidoException;

import java.math.BigDecimal;
import java.util.Arrays;

/**
 * Mensagem de entrada da fila de pedidos.
 * <p>
 * A validação é <b>explícita</b> ({@link #validar()}) e não feita no construtor canônico de
 * propósito: se o construtor lançasse, a falha ocorreria dentro da desserialização do Jackson, antes
 * de o listener ser invocado. Sem acesso ao {@code Acknowledgement}, a mensagem nunca seria
 * confirmada — resultando em reprocessamento infinito de uma mensagem que jamais terá sucesso.
 * Ver ADR-0001.
 *
 * <pre>{@code
 * {"idCliente":"C-1001","idPedido":"P-77","valorTotal":199.90,"quantidadeItens":3,
 *  "canal":"APP","fluxo":"PUBLICA_SNS"}
 * }</pre>
 */
public record PedidoEvent(
        String idCliente,
        String idPedido,
        BigDecimal valorTotal,
        Integer quantidadeItens,
        String canal,
        Fluxo fluxo) {

    /**
     * Rejeita o que nenhuma reentrega conserta: campo obrigatório ausente e valor fora do domínio.
     * <p>
     * As invariantes moram <b>aqui</b>, e não em anotações no adaptador de entrada, porque valem
     * para o pedido independentemente de ele ter chegado por SQS, por HTTP ou por um teste.
     *
     * @throws PedidoInvalidoException se o evento não puder ser processado (falha permanente)
     */
    public void validar() {
        if (idCliente == null || idCliente.isBlank()) {
            throw new PedidoInvalidoException("idCliente não pode ser nulo ou vazio");
        }
        if (idPedido == null || idPedido.isBlank()) {
            throw new PedidoInvalidoException("idPedido não pode ser nulo ou vazio");
        }
        if (valorTotal == null || valorTotal.signum() <= 0) {
            throw new PedidoInvalidoException("valorTotal deve ser maior que zero. Recebido: " + valorTotal);
        }
        if (quantidadeItens == null || quantidadeItens <= 0) {
            throw new PedidoInvalidoException("quantidadeItens deve ser maior que zero. Recebido: " + quantidadeItens);
        }
        if (fluxo == null) {
            throw new PedidoInvalidoException(
                    "fluxo inválido ou ausente. Valores permitidos: " + Arrays.toString(Fluxo.values()));
        }
    }
}
