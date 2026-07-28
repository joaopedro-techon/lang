package com.itau.sg2.custodiaposvenda.infrastructure.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.firehose")
public class FirehoseProperties {

    @NotBlank
    private String deliveryStreamName;

    /**
     * Endpoint alternativo do Firehose. Vazio em AWS real; apontado para o LocalStack no perfil
     * {@code local}. Sem isto não há como exercitar o fluxo fora da AWS.
     */
    private String endpoint;

    /** Teto de tempo da chamada inteira, incluindo os retries do próprio SDK. */
    @Min(1)
    private long apiCallTimeoutSegundos = 30;

    /** Teto por tentativa individual. Deve ser menor que {@link #apiCallTimeoutSegundos}. */
    @Min(1)
    private long apiCallAttemptTimeoutSegundos = 10;

    /** Tentativas do retry do SDK: rede, throttling, 5xx. */
    @Min(1)
    private int maxTentativas = 3;

    public String getDeliveryStreamName() { return deliveryStreamName; }

    public void setDeliveryStreamName(String deliveryStreamName) { this.deliveryStreamName = deliveryStreamName; }

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

    public int getMaxTentativas() { return maxTentativas; }

    public void setMaxTentativas(int maxTentativas) { this.maxTentativas = maxTentativas; }
}
