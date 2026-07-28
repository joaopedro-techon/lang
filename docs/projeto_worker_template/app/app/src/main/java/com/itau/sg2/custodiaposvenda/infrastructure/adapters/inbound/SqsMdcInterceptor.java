package com.itau.sg2.custodiaposvenda.infrastructure.adapters.inbound;

import com.itau.sg2.custodiaposvenda.shared.logging.MdcKeys;
import io.awspring.cloud.sqs.listener.interceptor.MessageInterceptor;
import org.slf4j.MDC;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.stereotype.Component;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Popula o MDC a partir dos atributos da mensagem.
 * <p>
 * Estava no pacote {@code infrastructure.logging}, junto com a fachada de log, embora seja um
 * interceptor do adaptador de entrada do SQS. Preencher o MDC é o efeito; o que a classe <b>é</b>
 * é parte da borda de entrada.
 */
@Component
public class SqsMdcInterceptor implements MessageInterceptor<Object> {

    /** Header na mensagem -> chave no MDC. Os headers do SQS chegam em minúsculas. */
    private static final Map<String, String> HEADER_PARA_MDC = Map.of(
            "correlationid", MdcKeys.CORRELATION_ID,
            "transactionid", MdcKeys.TRANSACTION_ID,
            "channel", MdcKeys.CHANNEL,
            "siglaapporigem", MdcKeys.SIGLA_APP_ORIGEM);

    private static final String PADRAO = "N/A";

    @Override
    public Message<Object> intercept(Message<Object> message) {
        Map<String, String> valores = extrairHeaders(message.getHeaders());

        MDC.put(MdcKeys.CORRELATION_ID, valorOuNovoId(valores.get(MdcKeys.CORRELATION_ID)));
        MDC.put(MdcKeys.TRANSACTION_ID, valorOuNovoId(valores.get(MdcKeys.TRANSACTION_ID)));
        MDC.put(MdcKeys.CHANNEL, valorOuPadrao(valores.get(MdcKeys.CHANNEL)));
        MDC.put(MdcKeys.SIGLA_APP_ORIGEM, valorOuPadrao(valores.get(MdcKeys.SIGLA_APP_ORIGEM)));

        return message;
    }

    @Override
    public void afterProcessing(Message<Object> message, Throwable t) {
        HEADER_PARA_MDC.values().forEach(MDC::remove);
    }

    /**
     * Uma única passagem pelos headers.
     * <p>
     * Antes eram quatro varreduras lineares por mensagem — uma por atributo procurado, cada uma
     * comparando com {@code equalsIgnoreCase} contra todos os headers. Com quatro atributos e um
     * caminho quente, o custo é multiplicado sem necessidade: os headers já são um mapa.
     */
    private Map<String, String> extrairHeaders(MessageHeaders headers) {
        Map<String, String> encontrados = new HashMap<>(HEADER_PARA_MDC.size());
        for (Map.Entry<String, Object> entry : headers.entrySet()) {
            String chaveMdc = HEADER_PARA_MDC.get(entry.getKey().toLowerCase());
            if (chaveMdc != null && entry.getValue() != null) {
                encontrados.put(chaveMdc, entry.getValue().toString());
            }
        }
        return encontrados;
    }

    private String valorOuNovoId(String valor) {
        return valor != null && !valor.isBlank() ? valor : UUID.randomUUID().toString();
    }

    private String valorOuPadrao(String valor) {
        return valor != null && !valor.isBlank() ? valor : PADRAO;
    }
}
