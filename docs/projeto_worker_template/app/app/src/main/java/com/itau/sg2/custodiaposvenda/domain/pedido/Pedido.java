package com.itau.sg2.custodiaposvenda.domain.pedido;

import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;

import java.time.Instant;
import java.util.Objects;

/**
 * Pedido pronto para publicação.
 * <p>
 * Virou {@code record}. A versão anterior era uma classe mutável com {@code marcarComoProcessado()}
 * alterando um estado (`processado`, `processadoEm`) que ninguém lia — a instância era descartada
 * logo em seguida — e com {@code equals}/{@code hashCode} escritos à mão e nunca usados. Estado
 * que não é lido não é modelagem: é ruído que sugere um ciclo de vida inexistente.
 * <p>
 * {@code criadoEm} chega por parâmetro, vindo de um {@link java.time.Clock} injetado, em vez de um
 * {@code LocalDateTime.now()} interno. Sem isso não há como escrever um teste determinístico sobre
 * o payload publicado. É {@link Instant}, e não {@code LocalDateTime}, porque o valor cruza a
 * fronteira do processo — sem fuso, o consumidor não sabe o que recebeu.
 */
public record Pedido(Long idOperacao, Fluxo fluxo, Instant criadoEm) {

    public Pedido {
        Objects.requireNonNull(idOperacao, "idOperacao não pode ser nulo");
        Objects.requireNonNull(fluxo, "fluxo não pode ser nulo");
        Objects.requireNonNull(criadoEm, "criadoEm não pode ser nulo");
    }

    public static Pedido de(PedidoEvent event, Instant criadoEm) {
        Objects.requireNonNull(event, "event não pode ser nulo");
        return new Pedido(event.idOperacao(), event.fluxo(), criadoEm);
    }
}
