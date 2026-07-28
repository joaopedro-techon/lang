package com.itau.sg2.custodiaposvenda.infrastructure.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * Tópico SNS de destino.
 * <p>
 * Preencher com o <b>ARN completo</b> ({@code arn:aws:sns:<região>:<conta>:<tópico>}). Ver
 * {@code SnsPublicador} para o porquê de não ser o nome do tópico.
 */
@Validated
@ConfigurationProperties(prefix = "app.sns")
public class SnsProperties {

    @NotBlank
    private String topicoPedido;

    public String getTopicoPedido() { return topicoPedido; }

    public void setTopicoPedido(String topicoPedido) { this.topicoPedido = topicoPedido; }
}
