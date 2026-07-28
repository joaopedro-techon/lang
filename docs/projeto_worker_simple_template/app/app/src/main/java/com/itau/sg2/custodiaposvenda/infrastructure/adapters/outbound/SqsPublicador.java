package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import com.itau.sg2.custodiaposvenda.application.ports.outbound.PublicadorPedidoPort;
import com.itau.sg2.custodiaposvenda.domain.pedido.Pedido;
import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;
import com.itau.sg2.custodiaposvenda.infrastructure.config.AppProperties;
import com.itau.sg2.custodiaposvenda.infrastructure.config.QueueProperties;
import com.itau.sg2.custodiaposvenda.shared.logging.Logger;
import com.itau.sg2.custodiaposvenda.shared.logging.PayloadLog;
import io.awspring.cloud.sqs.operations.SqsTemplate;
import org.springframework.stereotype.Component;

/**
 * Estratégia do fluxo {@link Fluxo#PUBLICA_SQS}: publica o pedido numa fila SQS de saída.
 * <p>
 * Fila de <b>saída</b>, distinta da fila de entrada consumida pelo listener. Publicar de volta na
 * fila de origem criaria um laço em que cada mensagem se reproduz — a fila nunca esvazia.
 */
@Component
public class SqsPublicador implements PublicadorPedidoPort {

    private final SqsTemplate sqsTemplate;
    private final QueueProperties queueProperties;
    private final AppProperties appProperties;

    public SqsPublicador(SqsTemplate sqsTemplate,
                         QueueProperties queueProperties,
                         AppProperties appProperties) {
        this.sqsTemplate = sqsTemplate;
        this.queueProperties = queueProperties;
        this.appProperties = appProperties;
    }

    @Override
    public Fluxo fluxoSuportado() {
        return Fluxo.PUBLICA_SQS;
    }

    @Override
    public void publicar(Pedido pedido) {
        String fila = queueProperties.getPublicacaoSqs();

        sqsTemplate.send(to -> to
                .queue(fila)
                .payload(pedido)
                .headers(CabecalhosPublicacao.de(appProperties.getSiglaApp())));

        Logger.info("Pedido publicado na fila SQS",
                PayloadLog.de("idCliente", pedido.idCliente())
                        .e("idPedido", pedido.idPedido())
                        .e("fila", fila));
    }
}
