package com.itau.sg2.custodiaposvenda.infrastructure.ratelimit;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.filter.OncePerRequestFilter;

import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

/**
 * Aplica o rate limit antes de qualquer processamento da request.
 *
 * <p>Fica bem no inicio da cadeia de proposito: o objetivo de rejeitar e nao
 * gastar CPU, thread pool e conexao de downstream com trafego excedente. Deixar
 * o limite depois da desserializacao ou da autenticacao pesada joga fora boa
 * parte do beneficio.
 */
public class RateLimitFilter extends OncePerRequestFilter {

    private static final String HEADER_LIMIT = "X-RateLimit-Limit";
    private static final String HEADER_REMAINING = "X-RateLimit-Remaining";

    private final RateLimiterService rateLimiterService;
    private final RateLimitProperties properties;

    public RateLimitFilter(RateLimiterService rateLimiterService, RateLimitProperties properties) {
        this.rateLimiterService = rateLimiterService;
        this.properties = properties;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        for (String excluded : properties.getExcludedPaths()) {
            if (path.startsWith(excluded)) {
                return true;
            }
        }
        return false;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {

        String apiKey = request.getHeader(properties.getHeaderName());
        RateLimitDecision decision = rateLimiterService.check(apiKey);

        if (decision.hasHeaders()) {
            response.setHeader(HEADER_LIMIT, Long.toString(decision.getLimit()));
            response.setHeader(HEADER_REMAINING, Long.toString(decision.getRemaining()));
        }

        if (decision.isAllowed()) {
            chain.doFilter(request, response);
            return;
        }

        writeTooManyRequests(response, decision);
    }

    private void writeTooManyRequests(HttpServletResponse response, RateLimitDecision decision) throws IOException {
        response.setStatus(HttpStatus.TOO_MANY_REQUESTS.value());
        response.setHeader(HttpHeaders.RETRY_AFTER, Long.toString(decision.getRetryAfterSeconds()));
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());

        String body = "{\"codigo\":\"RATE_LIMIT_EXCEEDED\","
                + "\"mensagem\":\"Limite de requisicoes excedido para esta api-key.\","
                + "\"limite\":" + decision.getLimit() + ","
                + "\"tenteEmSegundos\":" + decision.getRetryAfterSeconds() + "}";

        response.getWriter().write(body);
        response.getWriter().flush();
    }
}
