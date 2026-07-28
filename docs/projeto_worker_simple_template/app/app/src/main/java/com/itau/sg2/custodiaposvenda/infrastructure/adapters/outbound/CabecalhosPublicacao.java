package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import com.itau.sg2.custodiaposvenda.shared.logging.MdcHelper;
import com.itau.sg2.custodiaposvenda.shared.logging.MdcKeys;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Cabeçalhos de rastreabilidade propagados em toda mensagem publicada.
 * <p>
 * Os nomes são os mesmos que o {@code SqsMdcInterceptor} lê na entrada — é essa simetria que faz o
 * {@code correlationId} sobreviver de ponta a ponta da cadeia de serviços. Duplicar os literais em
 * cada publicador convidaria a divergirem, e o sintoma seria silencioso: a mensagem sai, o consumidor
 * gera um id novo, e a correlação simplesmente não existe sem nada falhar.
 * <p>
 * Minúsculas de propósito: é como os atributos chegam de volta pelo SQS.
 */
final class CabecalhosPublicacao {

    private static final String HEADER_CORRELATION_ID = "correlationid";
    private static final String HEADER_TRANSACTION_ID = "transactionid";
    private static final String HEADER_SIGLA_APP_ORIGEM = "siglaapporigem";

    private CabecalhosPublicacao() {
    }

    static Map<String, Object> de(String siglaApp) {
        Map<String, Object> cabecalhos = new LinkedHashMap<>();
        cabecalhos.put(HEADER_CORRELATION_ID, MdcHelper.mdcOrNew(MdcKeys.CORRELATION_ID));
        cabecalhos.put(HEADER_TRANSACTION_ID, MdcHelper.mdcOrNew(MdcKeys.TRANSACTION_ID));
        cabecalhos.put(HEADER_SIGLA_APP_ORIGEM, siglaApp);
        return cabecalhos;
    }
}
