package com.itau.sg2.custodiaposvenda.infrastructure.ratelimit;

/** Resultado da avaliacao de rate limit para uma request. */
public final class RateLimitDecision {

    /** Nao ha limite aplicavel (rate limit desligado ou api-key sem configuracao com politica ALLOW). */
    private static final RateLimitDecision NOT_LIMITED = new RateLimitDecision(true, -1, -1, 0, null);

    private final boolean allowed;
    private final long limit;
    private final long remaining;
    private final long retryAfterSeconds;
    private final String bucketId;

    private RateLimitDecision(boolean allowed, long limit, long remaining, long retryAfterSeconds, String bucketId) {
        this.allowed = allowed;
        this.limit = limit;
        this.remaining = remaining;
        this.retryAfterSeconds = retryAfterSeconds;
        this.bucketId = bucketId;
    }

    static RateLimitDecision notLimited() {
        return NOT_LIMITED;
    }

    static RateLimitDecision allowed(String bucketId, long limit, long remaining) {
        return new RateLimitDecision(true, limit, remaining, 0, bucketId);
    }

    static RateLimitDecision rejected(String bucketId, long limit, long retryAfterSeconds) {
        return new RateLimitDecision(false, limit, 0, retryAfterSeconds, bucketId);
    }

    public boolean isAllowed() { return allowed; }

    /** {@code -1} quando nao ha limite aplicavel. */
    public long getLimit() { return limit; }

    /** {@code -1} quando nao ha limite aplicavel. */
    public long getRemaining() { return remaining; }

    public long getRetryAfterSeconds() { return retryAfterSeconds; }

    /** {@code null} quando nao ha limite aplicavel. */
    public String getBucketId() { return bucketId; }

    boolean hasHeaders() {
        return limit >= 0;
    }
}
