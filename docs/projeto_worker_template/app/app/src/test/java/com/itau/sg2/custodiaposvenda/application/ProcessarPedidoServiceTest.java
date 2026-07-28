package com.itau.sg2.custodiaposvenda.application;

import com.itau.sg2.custodiaposvenda.application.ports.outbound.PublicadorMensagemPort;
import com.itau.sg2.custodiaposvenda.application.usecase.ProcessarPedidoService;
import com.itau.sg2.custodiaposvenda.domain.pedido.Pedido;
import com.itau.sg2.custodiaposvenda.domain.pedido.PedidoEvent;
import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;
import com.itau.sg2.custodiaposvenda.domain.pedido.exception.FluxoNaoSuportadoException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProcessarPedidoServiceTest {

    private static final Instant AGORA = Instant.parse("2026-07-28T12:00:00Z");
    private static final Clock CLOCK = Clock.fixed(AGORA, ZoneOffset.UTC);

    /** Publicador de teste que registra o que recebeu. */
    static class PublicadorFake implements PublicadorMensagemPort {
        private final Fluxo fluxo;
        final List<Pedido> recebidos = new ArrayList<>();

        PublicadorFake(Fluxo fluxo) { this.fluxo = fluxo; }

        @Override public Fluxo fluxoSuportado() { return fluxo; }

        @Override public void publicar(Pedido pedido) { recebidos.add(pedido); }
    }

    @Test
    @DisplayName("roteia para o publicador do fluxo do evento")
    void roteiaPorFluxo() {
        var sqs = new PublicadorFake(Fluxo.PUBLICA_SQS);
        var firehose = new PublicadorFake(Fluxo.DEMOCRATIZAR_FIREHOSE_BATCH);
        var service = new ProcessarPedidoService(List.of(sqs, firehose), CLOCK);

        service.executar(new PedidoEvent(7L, Fluxo.PUBLICA_SQS));

        assertEquals(1, sqs.recebidos.size());
        assertEquals(0, firehose.recebidos.size());
        assertEquals(7L, sqs.recebidos.getFirst().idOperacao());
    }

    @Test
    @DisplayName("carimba criadoEm com o Clock injetado")
    void usaClockInjetado() {
        var sqs = new PublicadorFake(Fluxo.PUBLICA_SQS);
        new ProcessarPedidoService(List.of(sqs), CLOCK)
                .executar(new PedidoEvent(1L, Fluxo.PUBLICA_SQS));

        assertEquals(AGORA, sqs.recebidos.getFirst().criadoEm());
    }

    @Test
    @DisplayName("fluxo sem publicador registrado vira falha permanente")
    void fluxoSemPublicador() {
        var service = new ProcessarPedidoService(List.of(new PublicadorFake(Fluxo.PUBLICA_SQS)), CLOCK);

        var ex = assertThrows(FluxoNaoSuportadoException.class,
                () -> service.executar(new PedidoEvent(1L, Fluxo.PUBLICA_KAFKA)));

        // Precisa ser permanente, senão a mensagem é reentregue para sempre em vez de ir à DLQ.
        assertTrue(ex instanceof com.itau.sg2.custodiaposvenda.domain.pedido.exception.PedidoNaoProcessavelException,
                "FluxoNaoSuportadoException deve ser classificada como falha permanente");
    }

    @Test
    @DisplayName("dois publicadores para o mesmo fluxo falham no startup, não em produção")
    void chaveDuplicadaFalhaNaConstrucao() {
        var a = new PublicadorFake(Fluxo.PUBLICA_SQS);
        var b = new PublicadorFake(Fluxo.PUBLICA_SQS);

        var ex = assertThrows(IllegalStateException.class,
                () -> new ProcessarPedidoService(List.of(a, b), CLOCK));

        assertTrue(ex.getMessage().contains("PUBLICA_SQS"),
                "a mensagem precisa dizer qual fluxo está duplicado: " + ex.getMessage());
    }

    @Test
    @DisplayName("publica a mesma instância de Pedido montada a partir do evento")
    void montaPedidoDoEvento() {
        var sqs = new PublicadorFake(Fluxo.PUBLICA_SQS);
        new ProcessarPedidoService(List.of(sqs), CLOCK)
                .executar(new PedidoEvent(99L, Fluxo.PUBLICA_SQS));

        Pedido esperado = new Pedido(99L, Fluxo.PUBLICA_SQS, AGORA);
        assertEquals(esperado, sqs.recebidos.getFirst());
        assertSame(Fluxo.PUBLICA_SQS, sqs.recebidos.getFirst().fluxo());
    }
}
