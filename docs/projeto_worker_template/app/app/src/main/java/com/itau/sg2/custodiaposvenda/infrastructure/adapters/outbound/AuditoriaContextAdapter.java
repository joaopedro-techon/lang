package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import com.itau.sg2.custodiaposvenda.application.ports.outbound.AuditoriaPort;
import com.itau.sg2.custodiaposvenda.domain.auditoria.EventoAuditoria;
import com.itau.sg2.custodiaposvenda.domain.auditoria.ParametrosAuditoria;
import com.itau.sg2.custodiaposvenda.infrastructure.config.AppProperties;
import com.itau.sg2.custodiaposvenda.shared.logging.Logger;
import com.itau.sg2.custodiaposvenda.shared.logging.MdcKeys;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;

import java.time.Clock;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.function.Supplier;

/**
 * Acumula a trilha de auditoria em {@link ThreadLocal}, por thread de processamento.
 * <p>
 * Era um singleton estático em {@code domain}. Continua com estado por thread — que é o que o
 * modelo exige — mas agora é um bean atrás de {@link AuditoriaPort}: o domínio não conhece mais
 * {@code ThreadLocal}, {@code MDC} nem serialização, e o estado deixa de ser global.
 * <p>
 * Todos os métodos engolem exceção e apenas logam: auditoria é trilha, não é o negócio. Uma falha
 * ao registrar não pode derrubar o processamento da mensagem.
 */
@Component
public class AuditoriaContextAdapter implements AuditoriaPort {

    private final ThreadLocal<List<EventoAuditoria>> eventos = new ThreadLocal<>();
    private final ThreadLocal<String> codigoProcessamento = new ThreadLocal<>();
    private final ThreadLocal<Long> idOperacao = new ThreadLocal<>();

    private final boolean ativa;
    private final Clock clock;

    public AuditoriaContextAdapter(AppProperties appProperties, Clock clock) {
        this.ativa = appProperties.getAuditoria().isAtiva();
        this.clock = clock;
    }

    @Override
    public void iniciar(Long idOperacao) {
        if (!ativa) {
            return;
        }
        try {
            this.eventos.set(new ArrayList<>());
            this.codigoProcessamento.set(UUID.randomUUID().toString());
            this.idOperacao.set(idOperacao);
        } catch (RuntimeException ex) {
            Logger.error("Erro ao iniciar contexto de auditoria.", ex);
        }
    }

    @Override
    public void registrar(Supplier<ParametrosAuditoria> parametros) {
        if (!ativa) {
            return;
        }
        try {
            List<EventoAuditoria> acumulados = eventos.get();
            if (acumulados == null) {
                return;
            }

            ParametrosAuditoria params = parametros.get();

            acumulados.add(new EventoAuditoria(
                    codigoProcessamento.get(),
                    MDC.get(MdcKeys.CORRELATION_ID),
                    idOperacao.get(),
                    params.situacao(),
                    params.detalhes(),
                    clock.instant()
            ));
        } catch (RuntimeException ex) {
            Logger.error("Erro ao registrar evento de auditoria.", ex);
        }
    }

    @Override
    public List<EventoAuditoria> drenar() {
        try {
            List<EventoAuditoria> acumulados = eventos.get();
            return acumulados != null ? List.copyOf(acumulados) : List.of();
        } catch (RuntimeException ex) {
            Logger.error("Erro ao obter eventos de auditoria.", ex);
            return List.of();
        } finally {
            limpar();
        }
    }

    private void limpar() {
        eventos.remove();
        codigoProcessamento.remove();
        idOperacao.remove();
    }
}
