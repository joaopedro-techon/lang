package com.itau.sg2.custodiaposvenda.domain.pedido.enums;

import com.fasterxml.jackson.annotation.JsonCreator;

import java.util.Arrays;

public enum Fluxo {
    DEMOCRATIZAR_FIREHOSE_BATCH,
    PUBLICA_SQS,
    PUBLICA_SNS,
    PUBLICA_KAFKA;

    /**
     * Converte um valor desconhecido em {@code null} em vez de lançar durante a desserialização.
     * <p>
     * O erro precisa aparecer no listener — onde há {@code Acknowledgement} e a mensagem pode ser
     * roteada para a DLQ — e não dentro do conversor do SQS, de onde a mensagem só poderia voltar
     * para a fila indefinidamente. A rejeição efetiva acontece em {@code PedidoEvent.validar()}.
     * <p>
     * A anotação vive no pacote {@code com.fasterxml.jackson.annotation}, comum ao Jackson 2 e ao
     * Jackson 3, e portanto vale para os dois mappers em uso na aplicação.
     */
    @JsonCreator
    public static Fluxo deValorTolerante(String valor) {
        return Arrays.stream(values())
                .filter(fluxo -> fluxo.name().equalsIgnoreCase(valor))
                .findFirst()
                .orElse(null);
    }
}
