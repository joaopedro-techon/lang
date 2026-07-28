package com.itau.sg2.custodiaposvenda.domain.pedido;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

/**
 * Pedido processado, pronto para publicação. É o payload que sai da aplicação.
 * <p>
 * Tipo distinto de {@link PedidoEvent} de propósito, apesar de os campos hoje coincidirem quase por
 * inteiro: um é o <b>contrato de entrada</b>, o outro o <b>contrato de saída</b>. Publicar o próprio
 * evento recebido amarra os dois — o dia em que a mensagem de entrada ganhar um campo interno, ele
 * vaza para todos os consumidores sem ninguém ter decidido isso.
 * <p>
 * {@code processadoEm} chega por parâmetro, vindo de um {@link java.time.Clock} injetado, em vez de
 * um {@code Instant.now()} interno: sem isso não há como escrever teste determinístico sobre o
 * payload publicado. É {@link Instant}, e não {@code LocalDateTime}, porque o valor cruza a
 * fronteira do processo — sem fuso, o consumidor não sabe o que recebeu.
 */
public record Pedido(
        String idCliente,
        String idPedido,
        BigDecimal valorTotal,
        int quantidadeItens,
        String canal,
        Instant processadoEm) {

    public Pedido {
        Objects.requireNonNull(idCliente, "idCliente não pode ser nulo");
        Objects.requireNonNull(idPedido, "idPedido não pode ser nulo");
        Objects.requireNonNull(valorTotal, "valorTotal não pode ser nulo");
        Objects.requireNonNull(processadoEm, "processadoEm não pode ser nulo");
    }

    /** Só faz sentido depois de {@link PedidoEvent#validar()}. */
    public static Pedido de(PedidoEvent event, Instant processadoEm) {
        Objects.requireNonNull(event, "event não pode ser nulo");

        return new Pedido(
                event.idCliente(),
                event.idPedido(),
                event.valorTotal(),
                event.quantidadeItens(),
                event.canal(),
                processadoEm);
    }
}
