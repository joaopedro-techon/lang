package com.itau.sg2.custodiaposvenda.application.ports.outbound;

import com.itau.sg2.custodiaposvenda.domain.auditoria.EventoAuditoria;
import com.itau.sg2.custodiaposvenda.domain.auditoria.ParametrosAuditoria;

import java.util.List;
import java.util.function.Supplier;

/**
 * Acúmulo da trilha de auditoria ao longo do processamento de uma mensagem.
 * <p>
 * Antes isto era um singleton estático mutável dentro de {@code domain}, com {@code ThreadLocal},
 * {@code MDC} e {@code ObjectMapper} — três detalhes técnicos num pacote que deveria ser puro, e
 * um estado global impossível de isolar em teste. Agora é uma porta: o domínio define o que se
 * registra, e o adaptador decide como esse estado é carregado.
 */
public interface AuditoriaPort {

    void iniciar(Long idOperacao);

    /**
     * O {@link Supplier} adia a montagem dos parâmetros: com a auditoria desligada, nada é
     * construído.
     */
    void registrar(Supplier<ParametrosAuditoria> parametros);

    /**
     * Devolve os eventos acumulados e encerra o contexto numa única operação.
     * <p>
     * Precisa ser chamado na <b>mesma thread</b> que os produziu. Publicar de forma assíncrona sem
     * drenar antes descarta a auditoria silenciosamente — foi o defeito corrigido no bloco 1, e a
     * assinatura existe para tornar o erro difícil de cometer.
     */
    List<EventoAuditoria> drenar();
}
