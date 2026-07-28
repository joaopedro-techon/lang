package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import com.itau.sg2.custodiaposvenda.application.ports.outbound.IdempotenciaPort;
import com.itau.sg2.custodiaposvenda.infrastructure.config.IdempotenciaProperties;
import com.itau.sg2.custodiaposvenda.shared.logging.Logger;
import com.itau.sg2.custodiaposvenda.shared.logging.PayloadLog;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.ConditionalCheckFailedException;
import software.amazon.awssdk.services.dynamodb.model.DeleteItemRequest;
import software.amazon.awssdk.services.dynamodb.model.PutItemRequest;

import java.time.Clock;
import java.util.Map;

/**
 * Idempotência sobre DynamoDB, usando escrita condicional como trava distribuída.
 * <p>
 * O DynamoDB foi escolhido por três razões concretas: a escrita condicional
 * ({@code attribute_not_exists}) é atômica e resolve a corrida entre duas tasks recebendo a mesma
 * duplicata ao mesmo tempo; o TTL nativo remove os registros sem job de limpeza; e não há cluster
 * para operar, ao contrário de um Redis.
 * <p>
 * <b>A trava é a condição, não o read-then-write.</b> Consultar antes e escrever depois teria uma
 * janela entre as duas operações — exatamente o intervalo em que a duplicata chega.
 */
@Component
public class DynamoDbIdempotenciaAdapter implements IdempotenciaPort {

    private static final String ATTR_CHAVE = "chave";
    private static final String ATTR_EXPIRA_EM = "expiraEm";
    private static final String ATTR_STATUS = "status";

    private static final String STATUS_EM_ANDAMENTO = "EM_ANDAMENTO";
    private static final String STATUS_CONCLUIDO = "CONCLUIDO";

    private final DynamoDbClient dynamoDbClient;
    private final IdempotenciaProperties properties;
    private final Clock clock;

    public DynamoDbIdempotenciaAdapter(DynamoDbClient dynamoDbClient,
                                       IdempotenciaProperties properties,
                                       Clock clock) {
        this.dynamoDbClient = dynamoDbClient;
        this.properties = properties;
        this.clock = clock;
    }

    @Override
    public boolean tentarIniciar(String chave) {
        if (!properties.isAtiva()) {
            return true;
        }

        try {
            dynamoDbClient.putItem(PutItemRequest.builder()
                    .tableName(properties.getTabela())
                    .item(item(chave, STATUS_EM_ANDAMENTO, properties.getTtlEmAndamentoSegundos()))
                    // Só grava se a chave não existir. É esta condição — avaliada pelo DynamoDB de
                    // forma atômica — que serializa duas tasks concorrentes.
                    .conditionExpression("attribute_not_exists(" + ATTR_CHAVE + ")")
                    .build());
            return true;
        } catch (ConditionalCheckFailedException ex) {
            Logger.info("Mensagem duplicada ignorada", PayloadLog.de("chaveIdempotencia", chave));
            return false;
        }
    }

    @Override
    public void concluir(String chave) {
        if (!properties.isAtiva()) {
            return;
        }

        // Sem condição: sobrescreve a marca provisória, estendendo o TTL para o prazo longo.
        dynamoDbClient.putItem(PutItemRequest.builder()
                .tableName(properties.getTabela())
                .item(item(chave, STATUS_CONCLUIDO, properties.getTtlHoras() * 3600))
                .build());
    }

    @Override
    public void liberar(String chave) {
        if (!properties.isAtiva()) {
            return;
        }

        try {
            dynamoDbClient.deleteItem(DeleteItemRequest.builder()
                    .tableName(properties.getTabela())
                    .key(Map.of(ATTR_CHAVE, AttributeValue.fromS(chave)))
                    .build());
        } catch (RuntimeException ex) {
            // Falhar aqui não pode mascarar a exceção original do processamento, que é a que
            // interessa. A marca provisória tem TTL curto justamente para este caso: ela expira
            // sozinha e a reentrega volta a ser aceita.
            Logger.warn("Não foi possível liberar a chave de idempotência; ela expirará pelo TTL.",
                    PayloadLog.de("chaveIdempotencia", chave), ex);
        }
    }

    private Map<String, AttributeValue> item(String chave, String status, long ttlSegundos) {
        long expiraEm = clock.instant().plusSeconds(ttlSegundos).getEpochSecond();
        return Map.of(
                ATTR_CHAVE, AttributeValue.fromS(chave),
                ATTR_STATUS, AttributeValue.fromS(status),
                // O TTL do DynamoDB exige epoch em SEGUNDOS, como Number. Gravar em
                // milissegundos faz a expiração cair no ano 57000 — e o registro nunca sai.
                ATTR_EXPIRA_EM, AttributeValue.fromN(Long.toString(expiraEm)));
    }
}
