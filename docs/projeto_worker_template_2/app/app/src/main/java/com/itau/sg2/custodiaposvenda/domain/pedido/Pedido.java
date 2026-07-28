package com.itau.sg2.custodiaposvenda.domain.pedido;

import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;

import java.time.LocalDateTime;
import java.util.Objects;

public class Pedido {

    private final Long idOperacao;
    private final Fluxo fluxo;
    private final LocalDateTime criadoEm;
    private boolean processado;
    private LocalDateTime processadoEm;

    private Pedido(Long idOperacao, Fluxo fluxo) {
        this.idOperacao = idOperacao;
        this.fluxo = fluxo;
        this.criadoEm = LocalDateTime.now();
        this.processado = false;
    }

    public static Pedido from(PedidoEvent event) {
        Objects.requireNonNull(event, "event não pode ser nulo");
        return new Pedido(event.idOperacao(), event.fluxo());
    }

    public void marcarComoProcessado() {
        if (this.processado) {
            throw new IllegalStateException("Pedido " + idOperacao + " já foi processado");
        }
        this.processado = true;
        this.processadoEm = LocalDateTime.now();
    }

    public boolean isProcessado() { return processado; }

    public Long getIdOperacao() { return idOperacao; }

    public Fluxo getFluxo() { return fluxo; }

    public LocalDateTime getCriadoEm() { return criadoEm; }

    public LocalDateTime getProcessadoEm() { return processadoEm; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof Pedido pedido)) return false;
        return Objects.equals(idOperacao, pedido.idOperacao);
    }

    @Override
    public int hashCode() { return Objects.hash(idOperacao); }
}
