package com.itau.sg2.custodiaposvenda.domain.auditoria;

import java.time.Instant;

public record EventoAuditoria(
        String codigoProcessamento,
        String correlationId,
        Long idOperacao,
        SituacaoAuditoria situacao,
        String detalhes,
        Instant dataHoraRegistro
) {
}
