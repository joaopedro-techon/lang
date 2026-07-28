package com.itau.sg2.custodiaposvenda.infrastructure.config;

import com.fasterxml.jackson.annotation.JsonInclude;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.SerializationFeature;
import tools.jackson.databind.cfg.DateTimeFeature;
import tools.jackson.databind.json.JsonMapper;

/**
 * Stack JSON da aplicação — Jackson 3 ({@code tools.jackson}).
 * <p>
 * O tipo do bean é {@link JsonMapper}, e não {@code ObjectMapper}, por um motivo concreto: o
 * {@code SqsAutoConfiguration} do awspring 4.0.0 monta o conversor de mensagens com
 * {@code jsonMapperProvider.getIfAvailable(JsonMapper::new)}. Com um bean {@code JsonMapper} no
 * contexto, ele usa <b>este</b>; sem ele, cai num {@code new JsonMapper()} de defaults.
 * <p>
 * Era exatamente o que acontecia enquanto este bean era um {@code ObjectMapper} do Jackson 2: as
 * configurações abaixo valiam para Firehose e auditoria, mas <b>não</b> para os payloads da fila,
 * e as duas stacks podiam divergir em silêncio. {@code JsonMapper} estende {@code ObjectMapper},
 * então quem injeta {@code ObjectMapper} continua recebendo este mesmo bean.
 * <p>
 * Notas de migração do Jackson 2:
 * <ul>
 *   <li>o mapper é imutável — configuração só via {@code builder()};</li>
 *   <li>{@code JavaTimeModule} não é mais registrado: o suporte a {@code java.time} é embutido
 *       no databind 3;</li>
 *   <li>{@code WRITE_DATES_AS_TIMESTAMPS} e {@code ADJUST_DATES_TO_CONTEXT_TIME_ZONE} saíram de
 *       {@code Serialization/DeserializationFeature} para {@link DateTimeFeature};</li>
 *   <li>as exceções passaram a ser unchecked ({@code JacksonException extends RuntimeException}).</li>
 * </ul>
 * O Jackson 2 continua no classpath, mas <b>apenas</b> como dependência transitiva do
 * logstash-logback-encoder, que serializa os logs. Nenhum código da aplicação o usa.
 */
@Configuration
public class JacksonConfig {

    @Bean
    @Primary
    public JsonMapper jsonMapper() {
        return JsonMapper.builder()
                .disable(DateTimeFeature.WRITE_DATES_AS_TIMESTAMPS)
                .disable(DateTimeFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE)
                .disable(SerializationFeature.FAIL_ON_EMPTY_BEANS)
                .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                .changeDefaultPropertyInclusion(
                        inclusao -> inclusao.withValueInclusion(JsonInclude.Include.NON_NULL))
                .build();
    }
}
