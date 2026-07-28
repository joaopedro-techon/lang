package com.itau.sg2.custodiaposvenda.domain.pedido.enums;

import com.fasterxml.jackson.annotation.JsonCreator;

import java.util.Arrays;

/**
 * Destino da publicação do pedido. É o campo que seleciona a estratégia de publicação.
 * <p>
 * <b>Contrato de mensagem.</b> Os nomes das constantes chegam como texto no JSON da fila: renomear
 * uma delas quebra todo produtor que já publica com o nome antigo. Cada valor declarado aqui precisa
 * ter exatamente um {@code PublicadorPedidoPort} correspondente — a aplicação avisa no startup
 * quando algum não tem.
 */
public enum Fluxo {

    PUBLICA_SNS,
    PUBLICA_SQS,
    PUBLICA_FIREHOSE;

    /**
     * Converte um valor desconhecido em {@code null} em vez de lançar durante a desserialização.
     * <p>
     * O erro precisa aparecer no listener — onde há {@code Acknowledgement} e a mensagem pode seguir
     * o ciclo até a DLQ — e não dentro do conversor do SQS, de onde a mensagem só poderia voltar
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
