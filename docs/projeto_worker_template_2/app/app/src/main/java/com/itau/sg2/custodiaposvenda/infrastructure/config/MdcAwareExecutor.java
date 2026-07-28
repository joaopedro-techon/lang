package com.itau.sg2.custodiaposvenda.infrastructure.config;

import org.slf4j.MDC;

import java.util.Map;
import java.util.concurrent.ExecutorService;

public class MdcAwareExecutor {

    private final ExecutorService delegate;

    public MdcAwareExecutor(ExecutorService delegate) { this.delegate = delegate; }

    public void execute(Runnable task) {
        Map<String, String> contextMap = MDC.getCopyOfContextMap();
        delegate.execute(() -> {
            if (contextMap != null) {
                MDC.setContextMap(contextMap);
            }
            try {
                task.run();
            } finally {
                MDC.clear();
            }
        });
    }

    public ExecutorService getDelegate() { return delegate; }
}
