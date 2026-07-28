package com.itau.sg2.custodiaposvenda.domain.auditoria;

import java.util.Map;

/** Dados de um registro de auditoria, antes de virar {@link EventoAuditoria}. */
public record ParametrosAuditoria(SituacaoAuditoria situacao, Map<String, Object> detalhes) {

    public ParametrosAuditoria(SituacaoAuditoria situacao) {
        this(situacao, Map.of());
    }

    public ParametrosAuditoria {
        detalhes = detalhes != null ? Map.copyOf(detalhes) : Map.of();
    }
}
