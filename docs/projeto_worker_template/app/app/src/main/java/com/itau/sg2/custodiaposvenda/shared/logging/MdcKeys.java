package com.itau.sg2.custodiaposvenda.shared.logging;

/**
 * Chaves do MDC.
 * <p>
 * Existiam como literais espalhados por quatro arquivos — o interceptor gravava, o
 * {@link Logger} lia, e nada garantia que fossem a mesma string. Um erro de digitação em qualquer
 * ponta produzia um campo silenciosamente vazio no log, não um erro.
 */
public final class MdcKeys {

    public static final String CORRELATION_ID = "CorrelationId";
    public static final String TRANSACTION_ID = "TransactionId";
    public static final String CHANNEL = "Channel";
    public static final String SIGLA_APP_ORIGEM = "SiglaAppOrigem";

    private MdcKeys() {
    }
}
