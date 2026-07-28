package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import com.itau.sg2.custodiaposvenda.application.ports.outbound.PublicadorAuditoriaPort;
import com.itau.sg2.custodiaposvenda.shared.logging.Logger;
import org.springframework.stereotype.Component;

import java.util.List;

@Component
public class FirehosePublicadorAuditoria implements PublicadorAuditoriaPort {

    private final FirehoseBatchClient firehoseBatchClient;
    private final FirehoseProperties firehoseProperties;

    public FirehosePublicadorAuditoria(FirehoseBatchClient firehoseBatchClient,
                                       FirehoseProperties firehoseProperties) {
        this.firehoseBatchClient = firehoseBatchClient;
        this.firehoseProperties = firehoseProperties;
    }

    @Override
    public <T> void publicar(List<T> eventos) {
        if (eventos == null || eventos.isEmpty()) {
            return;
        }

        firehoseBatchClient.enviarSincrono(firehoseProperties.getAuditoriaDeliveryStreamName(), eventos);

        Logger.info("Eventos de auditoria publicados no Firehose. quantidade=" + eventos.size());
    }
}
