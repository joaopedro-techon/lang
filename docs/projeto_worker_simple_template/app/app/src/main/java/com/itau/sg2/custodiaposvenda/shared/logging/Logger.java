package com.itau.sg2.custodiaposvenda.shared.logging;

import net.logstash.logback.marker.Markers;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.slf4j.Marker;

import java.time.Instant;
import java.util.Set;

/**
 * Fachada de log no formato corporativo.
 * <p>
 * Vive em {@code shared} de propósito. Log é preocupação transversal: se ficasse em
 * {@code infrastructure}, {@code domain} e {@code application} teriam de importar
 * {@code infrastructure} só para logar — que era exatamente a inversão da regra de dependência
 * hexagonal apontada na revisão. {@code shared} é o pacote que todas as camadas podem usar e que
 * não depende de nenhuma delas.
 * <p>
 * O payload é tipado como {@link PayloadLog}, e não {@code Object}: nenhuma sobrecarga aceita um
 * objeto de domínio inteiro, então dado sensível só entra no log se alguém nomear o campo.
 */
public final class Logger {

    /**
     * Inicializado com um logger padrão para que chamadas anteriores a {@link #configure} não gerem
     * NullPointerException (a ordem de inicialização de beans não é garantida). {@code volatile}
     * garante a visibilidade da reconfiguração para as demais threads.
     */
    private static volatile org.slf4j.Logger LOG = LoggerFactory.getLogger(Logger.class);
    private static final StackWalker STACK_WALKER = StackWalker.getInstance(Set.of(), 3);

    private static volatile String applicationName;
    private static volatile String serviceId;
    private static volatile String sigla;
    private static volatile String domain;

    private Logger() {
    }

    public static void configure(String loggerName, String applicationName, String serviceId, String sigla, String domain) {
        Logger.LOG = LoggerFactory.getLogger(loggerName);
        Logger.applicationName = applicationName;
        Logger.serviceId = serviceId;
        Logger.sigla = sigla;
        Logger.domain = domain;
    }

    public static void trace(String logMessage) {
        if (!LOG.isTraceEnabled()) return;
        LOG.trace(buildMarker("TRACE", logMessage, null, null), logMessage);
    }

    public static void trace(String logMessage, PayloadLog payload) {
        if (!LOG.isTraceEnabled()) return;
        LOG.trace(buildMarker("TRACE", logMessage, payload, null), logMessage);
    }

    public static void debug(String logMessage) {
        if (!LOG.isDebugEnabled()) return;
        LOG.debug(buildMarker("DEBUG", logMessage, null, null), logMessage);
    }

    public static void debug(String logMessage, PayloadLog payload) {
        if (!LOG.isDebugEnabled()) return;
        LOG.debug(buildMarker("DEBUG", logMessage, payload, null), logMessage);
    }

    public static void info(String logMessage) {
        if (!LOG.isInfoEnabled()) return;
        LOG.info(buildMarker("INFO", logMessage, null, null), logMessage);
    }

    public static void info(String logMessage, PayloadLog payload) {
        if (!LOG.isInfoEnabled()) return;
        LOG.info(buildMarker("INFO", logMessage, payload, null), logMessage);
    }

    public static void warn(String logMessage) {
        if (!LOG.isWarnEnabled()) return;
        LOG.warn(buildMarker("WARN", logMessage, null, null), logMessage);
    }

    public static void warn(String logMessage, PayloadLog payload) {
        if (!LOG.isWarnEnabled()) return;
        LOG.warn(buildMarker("WARN", logMessage, payload, null), logMessage);
    }

    public static void warn(String logMessage, Throwable throwable) {
        if (!LOG.isWarnEnabled()) return;
        LOG.warn(buildMarker("WARN", logMessage, null, throwable), logMessage, throwable);
    }

    public static void warn(String logMessage, PayloadLog payload, Throwable throwable) {
        if (!LOG.isWarnEnabled()) return;
        LOG.warn(buildMarker("WARN", logMessage, payload, throwable), logMessage, throwable);
    }

    public static void error(String logMessage) {
        if (!LOG.isErrorEnabled()) return;
        LOG.error(buildMarker("ERROR", logMessage, null, null), logMessage);
    }

    public static void error(String logMessage, PayloadLog payload) {
        if (!LOG.isErrorEnabled()) return;
        LOG.error(buildMarker("ERROR", logMessage, payload, null), logMessage);
    }

    /**
     * Sobrecarga dedicada a {@link Throwable}, para que a exceção seja logada com stacktrace em vez
     * de serializada como payload.
     */
    public static void error(String logMessage, Throwable throwable) {
        if (!LOG.isErrorEnabled()) return;
        LOG.error(buildMarker("ERROR", logMessage, null, throwable), logMessage, throwable);
    }

    public static void error(String logMessage, PayloadLog payload, Throwable throwable) {
        if (!LOG.isErrorEnabled()) return;
        LOG.error(buildMarker("ERROR", logMessage, payload, throwable), logMessage, throwable);
    }

    private static Marker buildMarker(String level, String logMessage, PayloadLog payload, Throwable throwable) {
        Log log = new Log();
        log.setApplicationName(applicationName);
        log.setServiceId(serviceId);
        log.setSigla(sigla);
        log.setDomain(domain);
        // A sigla de origem vem da mensagem (gravada no MDC pelo interceptor) e só cai na sigla
        // desta aplicação quando não houver. Antes usava sempre a própria sigla, o que tornava o
        // campo inútil: ele existe para identificar QUEM chamou.
        log.setSiglaAppOrigem(valorOuPadrao(MDC.get(MdcKeys.SIGLA_APP_ORIGEM), sigla));
        log.setChannel(MDC.get(MdcKeys.CHANNEL));
        // ISO-8601 em UTC. O formato anterior ("dd-MM-yyyy HH:mm:ss.SSS" sobre LocalDateTime) não
        // era ordenável lexicograficamente nem carregava fuso — dois defeitos sérios num log que
        // vai para agregador e é usado para correlacionar eventos entre serviços.
        log.setDateTime(Instant.now().toString());
        log.setCorrelationId(MDC.get(MdcKeys.CORRELATION_ID));
        log.setTransactionId(MDC.get(MdcKeys.TRANSACTION_ID));
        log.setLevel(level);
        log.setSeverity(level);
        log.setCodeLine(codeLineSeRelevante(level));
        log.setLogMessage(logMessage);
        log.setPayload(payload);
        log.setThrownException(throwable != null ? throwable.toString() : "");
        return Markers.appendFields(log);
    }

    private static String valorOuPadrao(String valor, String padrao) {
        return valor != null && !valor.isBlank() ? valor : padrao;
    }

    /**
     * O {@link StackWalker} só roda em WARN e ERROR.
     * <p>
     * Antes rodava em todo log, inclusive no INFO por mensagem consumida — o caminho quente deste
     * worker. A origem no código serve para localizar uma falha; num log de sucesso ela custa sem
     * pagar. Nos níveis em que é omitida o campo não aparece, porque {@link Log} é
     * {@code @JsonInclude(NON_EMPTY)}.
     */
    private static String codeLineSeRelevante(String level) {
        if (!"WARN".equals(level) && !"ERROR".equals(level)) {
            return null;
        }
        return STACK_WALKER.walk(frames -> frames
                .skip(3)
                .findFirst()
                .map(f -> f.getClassName() + " : " + f.getLineNumber())
                .orElse("unknown"));
    }
}
