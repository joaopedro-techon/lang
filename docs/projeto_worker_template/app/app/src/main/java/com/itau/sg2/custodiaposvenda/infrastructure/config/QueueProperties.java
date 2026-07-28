package com.itau.sg2.custodiaposvenda.infrastructure.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * Filas SQS.
 * <p>
 * {@code @Validated} não é enfeite: sem ele, um nome de fila ausente só se manifesta quando o
 * listener tenta resolver a fila — ou, pior, com {@code QueueNotFoundStrategy.FAIL}, num erro que
 * não diz que a causa foi configuração faltando. Com validação, a aplicação não sobe e a mensagem
 * aponta a propriedade.
 */
@Validated
@ConfigurationProperties(prefix = "app.queue")
public class QueueProperties {

    @NotBlank
    private String pedido;

    @Min(1)
    private int pedidoMaxConcurrent = 10;

    @NotBlank
    private String publicacaoSqs;

    public String getPedido() { return pedido; }

    public void setPedido(String pedido) { this.pedido = pedido; }

    public int getPedidoMaxConcurrent() { return pedidoMaxConcurrent; }

    public void setPedidoMaxConcurrent(int pedidoMaxConcurrent) { this.pedidoMaxConcurrent = pedidoMaxConcurrent; }

    public String getPublicacaoSqs() { return publicacaoSqs; }

    public void setPublicacaoSqs(String publicacaoSqs) { this.publicacaoSqs = publicacaoSqs; }
}
