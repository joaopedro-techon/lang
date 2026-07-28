package com.itau.sg2.custodiaposvenda.domain.pedido;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;
import com.itau.sg2.custodiaposvenda.domain.pedido.exception.PedidoInvalidoException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import java.time.Instant;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PedidoEventTest {

    @Nested
    @DisplayName("validar()")
    class Validar {

        @Test
        @DisplayName("aceita evento completo")
        void aceitaEventoCompleto() {
            assertDoesNotThrow(() -> new PedidoEvent(1L, Fluxo.PUBLICA_SQS).validar());
        }

        @Test
        @DisplayName("rejeita idOperacao nulo")
        void rejeitaIdNulo() {
            var ex = assertThrows(PedidoInvalidoException.class,
                    () -> new PedidoEvent(null, Fluxo.PUBLICA_SQS).validar());
            assertNotNull(ex.getMessage());
        }

        @Test
        @DisplayName("rejeita fluxo nulo e lista os valores permitidos")
        void rejeitaFluxoNulo() {
            var ex = assertThrows(PedidoInvalidoException.class,
                    () -> new PedidoEvent(1L, null).validar());
            assertTrueContem(ex.getMessage(), "PUBLICA_SQS");
        }

        /**
         * O construtor canônico NÃO valida — é o que permite ao listener capturar a falha com
         * acesso ao Acknowledgement. Se este teste quebrar, a mensagem inválida volta a explodir
         * dentro do Jackson e o ciclo de DLQ se perde (ADR-0001).
         */
        @Test
        @DisplayName("construtor aceita valores inválidos sem lançar")
        void construtorNaoValida() {
            assertDoesNotThrow(() -> new PedidoEvent(null, null));
        }
    }

    @Nested
    @DisplayName("Fluxo")
    class FluxoEnum {

        @Test
        @DisplayName("valor desconhecido vira null em vez de quebrar a desserialização")
        void valorDesconhecidoViraNull() {
            assertNull(Fluxo.deValorTolerante("NAO_EXISTE"));
        }

        @Test
        @DisplayName("valor nulo vira null")
        void valorNuloViraNull() {
            assertNull(Fluxo.deValorTolerante(null));
        }

        @Test
        @DisplayName("valor conhecido resolve")
        void valorConhecidoResolve() {
            assertEquals(Fluxo.PUBLICA_SQS, Fluxo.deValorTolerante("PUBLICA_SQS"));
        }

        /**
         * Garante que o método tolerante continua sendo o ponto de entrada do Jackson. Sem a
         * anotação, o Jackson volta ao comportamento padrão e lança em valor desconhecido.
         */
        @Test
        @DisplayName("o factory tolerante está anotado com @JsonCreator")
        void factoryAnotado() throws NoSuchMethodException {
            var metodo = Fluxo.class.getDeclaredMethod("deValorTolerante", String.class);
            assertNotNull(metodo.getAnnotation(JsonCreator.class),
                    "sem @JsonCreator o Jackson não usa este factory e a tolerância some");
        }
    }

    @Nested
    @DisplayName("Pedido")
    class PedidoRecord {

        @Test
        @DisplayName("de() copia os campos do evento")
        void deCopiaCampos() {
            Instant agora = Instant.parse("2026-07-28T10:00:00Z");
            Pedido pedido = Pedido.de(new PedidoEvent(42L, Fluxo.PUBLICA_SQS), agora);

            assertEquals(42L, pedido.idOperacao());
            assertEquals(Fluxo.PUBLICA_SQS, pedido.fluxo());
            assertEquals(agora, pedido.criadoEm());
        }

        @Test
        @DisplayName("rejeita construção com campo nulo")
        void rejeitaNulos() {
            Instant agora = Instant.EPOCH;
            assertThrows(NullPointerException.class, () -> new Pedido(null, Fluxo.PUBLICA_SQS, agora));
            assertThrows(NullPointerException.class, () -> new Pedido(1L, null, agora));
            assertThrows(NullPointerException.class, () -> new Pedido(1L, Fluxo.PUBLICA_SQS, null));
        }

        @Test
        @DisplayName("criadoEm vem de fora, não do relógio da máquina")
        void criadoEmDeterministico() {
            Instant fixo = Instant.parse("2000-01-01T00:00:00Z");
            assertEquals(fixo, Pedido.de(new PedidoEvent(1L, Fluxo.PUBLICA_SQS), fixo).criadoEm());
        }
    }

    private static void assertTrueContem(String texto, String trecho) {
        org.junit.jupiter.api.Assertions.assertTrue(
                texto != null && texto.contains(trecho),
                "esperava encontrar '" + trecho + "' em: " + texto);
    }
}
