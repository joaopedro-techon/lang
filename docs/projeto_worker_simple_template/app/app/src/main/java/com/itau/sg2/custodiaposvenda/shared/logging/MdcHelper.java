package com.itau.sg2.custodiaposvenda.shared.logging;

import org.slf4j.MDC;

import java.util.UUID;

public final class MdcHelper {

    private MdcHelper() {
    }

    /**
     * Valor do MDC, ou um id novo <b>já gravado no MDC</b> caso não exista.
     * <p>
     * A gravação é essencial: a versão anterior apenas devolvia um {@code UUID} novo sem
     * registrá-lo, então uma mensagem publicada saía com um correlation id que não aparecia em
     * nenhum log — inútil justamente para o que o id serve, que é correlacionar.
     */
    public static String mdcOrNew(String key) {
        String value = MDC.get(key);
        if (value != null) {
            return value;
        }
        String novo = UUID.randomUUID().toString();
        MDC.put(key, novo);
        return novo;
    }
}
