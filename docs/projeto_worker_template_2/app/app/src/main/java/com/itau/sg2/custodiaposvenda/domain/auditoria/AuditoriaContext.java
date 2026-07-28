package com.itau.sg2.custodiaposvenda.domain.auditoria;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.itau.sg2.custodiaposvenda.infrastructure.logging.Logger;
import org.slf4j.MDC;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Supplier;

public final class AuditoriaContext {

    private static final ThreadLocal<List<EventoAuditoria>> EVENTOS = new ThreadLocal<>();
    private static final ThreadLocal<String> CODIGO_PROCESSAMENTO = new ThreadLocal<>();
    private static final ThreadLocal<Boolean> ATIVA = new ThreadLocal<>();
    private static final ThreadLocal<Long> ID_OPERACAO = new ThreadLocal<>();

    private static ObjectMapper objectMapper;

    private AuditoriaContext() {
    }

    public static void configurarObjectMapper(ObjectMapper mapper) { objectMapper = mapper; }

    public static void iniciar(boolean ativa, Long idOperacao) {
        try {
            ATIVA.set(ativa);
            if (!ativa) {
                return;
            }
            EVENTOS.set(new ArrayList<>());
            CODIGO_PROCESSAMENTO.set(UUID.randomUUID().toString());
            ID_OPERACAO.set(idOperacao);
        } catch (Exception ex) {
            Logger.error("Erro ao iniciar contexto de auditoria.", ex);
        }
    }

    public static void registrar(Supplier<ParametrosAuditoria> supplier) {
        try {
            if (!Boolean.TRUE.equals(ATIVA.get())) {
                return;
            }

            List<EventoAuditoria> eventos = EVENTOS.get();
            if (eventos == null) {
                return;
            }

            ParametrosAuditoria params = supplier.get();

            String detalhesJson = "{}";
            if (params.detalhes() != null && !params.detalhes().isEmpty()) {
                detalhesJson = objectMapper.writeValueAsString(params.detalhes());
            }

            EventoAuditoria evento = new EventoAuditoria(
                    CODIGO_PROCESSAMENTO.get(),
                    MDC.get("CorrelationId"),
                    ID_OPERACAO.get(),
                    params.situacao(),
                    detalhesJson,
                    Instant.now()
            );

            eventos.add(evento);
        } catch (Exception ex) {
            Logger.error("Erro ao registrar evento de auditoria.", ex);
        }
    }

    public record ParametrosAuditoria(SituacaoAuditoria situacao, Map<String, Object> detalhes) {
        public ParametrosAuditoria(SituacaoAuditoria situacao) { this(situacao, null); }
    }

    public static List<EventoAuditoria> obterEventos() {
        try {
            List<EventoAuditoria> eventos = EVENTOS.get();
            return eventos != null ? Collections.unmodifiableList(eventos) : Collections.emptyList();
        } catch (Exception ex) {
            Logger.error("Erro ao obter eventos de auditoria.", ex);
            return Collections.emptyList();
        }
    }

    public static void limpar() {
        try {
            EVENTOS.remove();
            CODIGO_PROCESSAMENTO.remove();
            ATIVA.remove();
            ID_OPERACAO.remove();
        } catch (Exception ex) {
            Logger.error("Erro ao limpar contexto de auditoria.", ex);
        }
    }
}
