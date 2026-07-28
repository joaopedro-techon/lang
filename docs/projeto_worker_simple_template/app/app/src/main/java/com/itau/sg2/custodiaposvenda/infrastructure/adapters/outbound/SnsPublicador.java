package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import com.itau.sg2.custodiaposvenda.application.ports.outbound.PublicadorPedidoPort;
import com.itau.sg2.custodiaposvenda.domain.pedido.Pedido;
import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;
import com.itau.sg2.custodiaposvenda.infrastructure.config.AppProperties;
import com.itau.sg2.custodiaposvenda.infrastructure.config.SnsProperties;
import com.itau.sg2.custodiaposvenda.shared.logging.Logger;
import com.itau.sg2.custodiaposvenda.shared.logging.PayloadLog;
import io.awspring.cloud.sns.core.SnsTemplate;
import org.springframework.stereotype.Component;

/**
 * Estratégia do fluxo {@link Fluxo#PUBLICA_SNS}: publica o pedido no tópico SNS.
 * <p>
 * O tópico é configurado pelo <b>ARN completo</b>, não pelo nome. Com um nome, o awspring precisa
 * resolvê-lo em ARN chamando {@code CreateTopic} — que é idempotente, mas exige a permissão
 * {@code sns:CreateTopic} na task role e criaria o tópico errado em silêncio se o nome viesse com um
 * typo. Com o ARN, a publicação usa só {@code sns:Publish}.
 */
@Component
public class SnsPublicador implements PublicadorPedidoPort {

    private final SnsTemplate snsTemplate;
    private final SnsProperties snsProperties;
    private final AppProperties appProperties;

    public SnsPublicador(SnsTemplate snsTemplate, SnsProperties snsProperties, AppProperties appProperties) {
        this.snsTemplate = snsTemplate;
        this.snsProperties = snsProperties;
        this.appProperties = appProperties;
    }

    @Override
    public Fluxo fluxoSuportado() {
        return Fluxo.PUBLICA_SNS;
    }

    @Override
    public void publicar(Pedido pedido) {
        String topico = snsProperties.getTopicoPedido();

        snsTemplate.convertAndSend(topico, pedido, CabecalhosPublicacao.de(appProperties.getSiglaApp()));

        Logger.info("Pedido publicado no tópico SNS",
                PayloadLog.de("idCliente", pedido.idCliente())
                        .e("idPedido", pedido.idPedido())
                        .e("topico", topico));
    }
}
