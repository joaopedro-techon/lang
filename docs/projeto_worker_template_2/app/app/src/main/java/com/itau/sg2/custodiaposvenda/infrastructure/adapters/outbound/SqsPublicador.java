package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import com.itau.sg2.custodiaposvenda.application.ports.outbound.PublicadorMensagemPort;
import com.itau.sg2.custodiaposvenda.domain.pedido.Pedido;
import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;
import com.itau.sg2.custodiaposvenda.infrastructure.config.AppProperties;
import com.itau.sg2.custodiaposvenda.infrastructure.config.QueueProperties;
import com.itau.sg2.custodiaposvenda.infrastructure.logging.Logger;
import com.itau.sg2.custodiaposvenda.infrastructure.logging.MdcHelper;
import io.awspring.cloud.sqs.operations.SqsTemplate;
import org.springframework.stereotype.Component;

@Component
public class SqsPublicador implements PublicadorMensagemPort {

    private static final String HEADER_CORRELATION_ID = "correlationid";
    private static final String HEADER_TRANSACTION_ID = "transactionid";
    private static final String HEADER_SIGLA_APP_ORIGEM = "siglaapporigem";

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
    public Fluxo fluxoSuportado() { return Fluxo.PUBLICA_SQS; }

    @Override
    public void publicar(Pedido pedido) {
        String queueName = queueProperties.getPublicacaoSqs();

        sqsTemplate.send(to -> to
                .queue(queueName)
                .payload(pedido)
                .header(HEADER_CORRELATION_ID, MdcHelper.mdcOrNew("CorrelationId"))
                .header(HEADER_TRANSACTION_ID, MdcHelper.mdcOrNew("TransactionId"))
                .header(HEADER_SIGLA_APP_ORIGEM, appProperties.getSiglaApp()));

        Logger.info("Mensagem publicada na fila SQS. queue=" + queueName, pedido);
    }
}
