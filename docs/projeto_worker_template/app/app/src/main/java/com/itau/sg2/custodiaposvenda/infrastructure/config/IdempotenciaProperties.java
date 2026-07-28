package com.itau.sg2.custodiaposvenda.infrastructure.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.idempotencia")
public class IdempotenciaProperties {

    /**
     * Desligar só faz sentido em cenário onde a publicação já é idempotente no destino. Note que
     * desligado significa aceitar publicação duplicada, não "sem efeito".
     */
    private boolean ativa = true;

    @NotBlank
    private String tabela = "msdemoworker-idempotencia";

    /** Endpoint alternativo — LocalStack no perfil local. Vazio em AWS real. */
    private String endpoint;

    /**
     * Por quanto tempo a marca definitiva sobrevive. Precisa ser confortavelmente maior que a
     * janela em que uma duplicata pode chegar: retention da fila + reentregas até a DLQ.
     */
    @Min(1)
    private long ttlHoras = 72;

    /**
     * TTL da marca provisória, criada por {@code tentarIniciar}. É a rede de segurança para o caso
     * de o processo morrer entre iniciar e concluir/liberar: sem ela a chave ficaria travada até o
     * TTL longo expirar, e toda reentrega seria descartada como duplicata nesse meio tempo.
     * <p>
     * Deve ser maior que o pior tempo de processamento e menor que o visibility timeout da fila.
     */
    @Min(1)
    private long ttlEmAndamentoSegundos = 300;

    public boolean isAtiva() { return ativa; }

    public void setAtiva(boolean ativa) { this.ativa = ativa; }

    public String getTabela() { return tabela; }

    public void setTabela(String tabela) { this.tabela = tabela; }

    public String getEndpoint() { return endpoint; }

    public void setEndpoint(String endpoint) { this.endpoint = endpoint; }

    public long getTtlHoras() { return ttlHoras; }

    public void setTtlHoras(long ttlHoras) { this.ttlHoras = ttlHoras; }

    public long getTtlEmAndamentoSegundos() { return ttlEmAndamentoSegundos; }

    public void setTtlEmAndamentoSegundos(long ttlEmAndamentoSegundos) {
        this.ttlEmAndamentoSegundos = ttlEmAndamentoSegundos;
    }
}
