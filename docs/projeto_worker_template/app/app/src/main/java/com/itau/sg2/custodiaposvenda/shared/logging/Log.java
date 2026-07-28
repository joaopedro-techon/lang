package com.itau.sg2.custodiaposvenda.shared.logging;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonInclude(JsonInclude.Include.NON_EMPTY)
public class Log {

    @JsonProperty("ApplicationName")
    private String applicationName;

    @JsonProperty("ServiceId")
    private String serviceId;

    @JsonProperty("Sigla")
    private String sigla;

    @JsonProperty("Domain")
    private String domain;

    @JsonProperty("SiglaAppOrigem")
    private String siglaAppOrigem;

    @JsonProperty("Channel")
    private String channel;

    @JsonProperty("DateTime")
    private String dateTime;

    @JsonProperty("CorrelationId")
    private String correlationId;

    @JsonProperty("TransactionId")
    private String transactionId;

    @JsonProperty("Level")
    private String level;

    @JsonProperty("Severity")
    private String severity;

    @JsonProperty("CodeLine")
    private String codeLine;

    @JsonProperty("LogMessage")
    private String logMessage;

    /** Ver {@link PayloadLog} — tipado de propósito, para não aceitar objeto de domínio inteiro. */
    @JsonProperty("Payload")
    private PayloadLog payload;

    @JsonProperty("ThrownException")
    private String thrownException;

    Log() {
    }

    public String getApplicationName() { return applicationName; }

    public void setApplicationName(String applicationName) { this.applicationName = applicationName; }

    public String getServiceId() { return serviceId; }

    public void setServiceId(String serviceId) { this.serviceId = serviceId; }

    public String getSigla() { return sigla; }

    public void setSigla(String sigla) { this.sigla = sigla; }

    public String getDomain() { return domain; }

    public void setDomain(String domain) { this.domain = domain; }

    public String getSiglaAppOrigem() { return siglaAppOrigem; }

    public void setSiglaAppOrigem(String siglaAppOrigem) { this.siglaAppOrigem = siglaAppOrigem; }

    public String getChannel() { return channel; }

    public void setChannel(String channel) { this.channel = channel; }

    public String getDateTime() { return dateTime; }

    public void setDateTime(String dateTime) { this.dateTime = dateTime; }

    public String getCorrelationId() { return correlationId; }

    public void setCorrelationId(String correlationId) { this.correlationId = correlationId; }

    public String getTransactionId() { return transactionId; }

    public void setTransactionId(String transactionId) { this.transactionId = transactionId; }

    public String getLevel() { return level; }

    public void setLevel(String level) { this.level = level; }

    public String getSeverity() { return severity; }

    public void setSeverity(String severity) { this.severity = severity; }

    public String getCodeLine() { return codeLine; }

    public void setCodeLine(String codeLine) { this.codeLine = codeLine; }

    public String getLogMessage() { return logMessage; }

    public void setLogMessage(String logMessage) { this.logMessage = logMessage; }

    public PayloadLog getPayload() { return payload; }

    public void setPayload(PayloadLog payload) { this.payload = payload; }

    public String getThrownException() { return thrownException; }

    public void setThrownException(String thrownException) { this.thrownException = thrownException; }
}
