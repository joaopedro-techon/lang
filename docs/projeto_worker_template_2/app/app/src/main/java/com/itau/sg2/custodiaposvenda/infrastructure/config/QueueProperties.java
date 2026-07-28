package com.itau.sg2.custodiaposvenda.infrastructure.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.queue")
public class QueueProperties {

    private String pedido;
    private String pedidoMaxConcurrent;
    private String publicacaoSqs;

    public String getPedido() { return pedido; }

    public void setPedido(String pedido) { this.pedido = pedido; }

    public String getPedidoMaxConcurrent() { return pedidoMaxConcurrent; }

    public void setPedidoMaxConcurrent(String pedidoMaxConcurrent) { this.pedidoMaxConcurrent = pedidoMaxConcurrent; }

    public String getPublicacaoSqs() { return publicacaoSqs; }

    public void setPublicacaoSqs(String publicacaoSqs) { this.publicacaoSqs = publicacaoSqs; }
}
