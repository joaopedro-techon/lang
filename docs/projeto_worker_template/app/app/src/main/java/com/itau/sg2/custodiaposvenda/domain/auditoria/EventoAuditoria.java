package com.itau.sg2.custodiaposvenda.domain.auditoria;

import java.time.Instant;
import java.util.Map;

/**
 * Evento da trilha de auditoria.
 * <p>
 * {@code detalhes} é um {@code Map}, não uma {@code String} de JSON já serializado. Serializar era
 * o que obrigava o domínio a conhecer um {@code ObjectMapper}; agora quem serializa é o publicador,
 * na camada de infraestrutura, que já tem o mapper e sabe o formato do destino.
 */
public record EventoAuditoria(
        String codigoProcessamento,
        String correlationId,
        Long idOperacao,
        SituacaoAuditoria situacao,
        Map<String, Object> detalhes,
        Instant dataHoraRegistro
) {
    public EventoAuditoria {
        detalhes = detalhes != null ? Map.copyOf(detalhes) : Map.of();
    }
}
