package com.itau.sg2.custodiaposvenda.infrastructure.logging;

import net.logstash.logback.marker.Markers;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.slf4j.Marker;

import java.lang.StackWalker.StackFrame;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Set;

public final class Logger {

    private static org.slf4j.Logger LOG;
    private static final StackWalker STACK_WALKER = StackWalker.getInstance(Set.of(), 3);
    private static final DateTimeFormatter DATE_TIME_FORMATTER = DateTimeFormatter.ofPattern("dd-MM-yyyy HH:mm:ss.SSS");

    private static String applicationName;
    private static String serviceId;
    private static String sigla;
    private static String domain;

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
        LOG.trace(buildMarker("TRACE", "TRACE", logMessage, null, null), logMessage);
    }

    public static void trace(String logMessage, Object payload) {
        if (!LOG.isTraceEnabled()) return;
        LOG.trace(buildMarker("TRACE", "TRACE", logMessage, payload, null), logMessage);
    }

    public static void debug(String logMessage) {
        if (!LOG.isDebugEnabled()) return;
        LOG.debug(buildMarker("DEBUG", "DEBUG", logMessage, null, null), logMessage);
    }

    public static void debug(String logMessage, Object payload) {
        if (!LOG.isDebugEnabled()) return;
        LOG.debug(buildMarker("DEBUG", "DEBUG", logMessage, payload, null), logMessage);
    }

    public static void info(String logMessage) {
        if (!LOG.isInfoEnabled()) return;
        LOG.info(buildMarker("INFO", "INFO", logMessage, null, null), logMessage);
    }

    public static void info(String logMessage, Object payload) {
        if (!LOG.isInfoEnabled()) return;
        LOG.info(buildMarker("INFO", "INFO", logMessage, payload, null), logMessage);
    }

    public static void warn(String logMessage) {
        if (!LOG.isWarnEnabled()) return;
        LOG.warn(buildMarker("WARN", "WARN", logMessage, null, null), logMessage);
    }

    public static void warn(String logMessage, Object payload) {
        if (!LOG.isWarnEnabled()) return;
        LOG.warn(buildMarker("WARN", "WARN", logMessage, payload, null), logMessage);
    }

    public static void warn(String logMessage, Object payload, Throwable throwable) {
        if (!LOG.isWarnEnabled()) return;
        LOG.warn(buildMarker("WARN", "WARN", logMessage, payload, throwable), logMessage, throwable);
    }

    public static void error(String logMessage) {
        if (!LOG.isErrorEnabled()) return;
        LOG.error(buildMarker("ERROR", "ERROR", logMessage, null, null), logMessage);
    }

    public static void error(String logMessage, Object payload) {
        if (!LOG.isErrorEnabled()) return;
        LOG.error(buildMarker("ERROR", "ERROR", logMessage, payload, null), logMessage);
    }

    public static void error(String logMessage, Object payload, Throwable throwable) {
        if (!LOG.isErrorEnabled()) return;
        LOG.error(buildMarker("ERROR", "ERROR", logMessage, payload, throwable), logMessage, throwable);
    }

    private static Marker buildMarker(String level, String severity, String logMessage, Object payload, Throwable throwable) {
        Log log = new Log();
        log.setApplicationName(applicationName);
        log.setServiceId(serviceId);
        log.setSigla(sigla);
        log.setDomain(domain);
        log.setSiglaAppOrigem(sigla);
        log.setChannel(MDC.get("Channel"));
        log.setDateTime(LocalDateTime.now().format(DATE_TIME_FORMATTER));
        log.setCorrelationId(MDC.get("CorrelationId"));
        log.setTransactionId(MDC.get("TransactionId"));
        log.setLevel(level);
        log.setSeverity(severity);
        log.setCodeLine(getCallerCodeLine());
        log.setLogMessage(logMessage);
        log.setPayload(payload);
        log.setThrownException(throwable != null ? throwable.toString() : "");
        return Markers.appendFields(log);
    }

    private static String getCallerCodeLine() {
        return STACK_WALKER.walk(frames -> frames
                .skip(3)
                .findFirst()
                .map(f -> f.getClassName() + " : " + f.getLineNumber())
                .orElse("unknown"));
    }
}
