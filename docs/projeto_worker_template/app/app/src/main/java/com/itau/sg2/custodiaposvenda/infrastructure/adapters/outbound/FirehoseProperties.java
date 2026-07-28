package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.firehose")
public class FirehoseProperties {

    private String deliveryStreamName;
    private String auditoriaDeliveryStreamName;

    /** Total de tentativas por batch, incluindo a primeira, quando há registros rejeitados. */
    private int maxTentativas = 3;

    /** Base do backoff exponencial entre reenvios (ms): 200, 400, 800... */
    private long backoffInicialMs = 200;

    /**
     * Endpoint alternativo do Firehose. Vazio em AWS real; apontado para o LocalStack no perfil
     * {@code local}. Sem isto não há como exercitar o fluxo fora da AWS.
     */
    private String endpoint;

    /**
     * Teto de tempo da chamada inteira, incluindo os retries do próprio SDK. Sem ele o
     * {@code join()} do publicador pode ficar preso indefinidamente segurando uma thread do
     * listener.
     */
    private long apiCallTimeoutSegundos = 30;

    /** Teto por tentativa individual. Deve ser menor que {@link #apiCallTimeoutSegundos}. */
    private long apiCallAttemptTimeoutSegundos = 10;

    /**
     * Tentativas do retry do SDK (rede, throttling no nível HTTP). É diferente de
     * {@link #maxTentativas}, que trata dos registros rejeitados <i>dentro</i> de uma resposta 200.
     */
    private int maxTentativasSdk = 3;

    public String getDeliveryStreamName() { return deliveryStreamName; }

    public void setDeliveryStreamName(String deliveryStreamName) { this.deliveryStreamName = deliveryStreamName; }

    public String getAuditoriaDeliveryStreamName() { return auditoriaDeliveryStreamName; }

    public void setAuditoriaDeliveryStreamName(String auditoriaDeliveryStreamName) {
        this.auditoriaDeliveryStreamName = auditoriaDeliveryStreamName;
    }

    public int getMaxTentativas() { return maxTentativas; }

    public void setMaxTentativas(int maxTentativas) { this.maxTentativas = maxTentativas; }

    public long getBackoffInicialMs() { return backoffInicialMs; }

    public void setBackoffInicialMs(long backoffInicialMs) { this.backoffInicialMs = backoffInicialMs; }

    public String getEndpoint() { return endpoint; }

    public void setEndpoint(String endpoint) { this.endpoint = endpoint; }

    public long getApiCallTimeoutSegundos() { return apiCallTimeoutSegundos; }

    public void setApiCallTimeoutSegundos(long apiCallTimeoutSegundos) {
        this.apiCallTimeoutSegundos = apiCallTimeoutSegundos;
    }

    public long getApiCallAttemptTimeoutSegundos() { return apiCallAttemptTimeoutSegundos; }

    public void setApiCallAttemptTimeoutSegundos(long apiCallAttemptTimeoutSegundos) {
        this.apiCallAttemptTimeoutSegundos = apiCallAttemptTimeoutSegundos;
    }

    public int getMaxTentativasSdk() { return maxTentativasSdk; }

    public void setMaxTentativasSdk(int maxTentativasSdk) { this.maxTentativasSdk = maxTentativasSdk; }
}
