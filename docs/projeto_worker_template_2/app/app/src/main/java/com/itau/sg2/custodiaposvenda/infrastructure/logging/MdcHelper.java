package com.itau.sg2.custodiaposvenda.infrastructure.logging;

import org.slf4j.MDC;

import java.util.UUID;

public final class MdcHelper {

    private MdcHelper() {
    }

    public static String mdcOrNew(String key) {
        String value = MDC.get(key);
        return value != null ? value : UUID.randomUUID().toString();
    }
}
