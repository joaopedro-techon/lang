package com.itau.sg2.custodiaposvenda.application;

import com.itau.sg2.custodiaposvenda.application.facade.ProcessarPedidoFacade;
import com.itau.sg2.custodiaposvenda.application.ports.inbound.ProcessarPedidoUseCasePort;
import com.itau.sg2.custodiaposvenda.application.ports.outbound.AuditoriaPort;
import com.itau.sg2.custodiaposvenda.application.ports.outbound.ExecutorAssincronoPort;
import com.itau.sg2.custodiaposvenda.application.ports.outbound.IdempotenciaPort;
import com.itau.sg2.custodiaposvenda.application.ports.outbound.MetricasPort;
import com.itau.sg2.custodiaposvenda.application.ports.outbound.PublicadorAuditoriaPort;
import com.itau.sg2.custodiaposvenda.domain.auditoria.EventoAuditoria;
import com.itau.sg2.custodiaposvenda.domain.auditoria.ParametrosAuditoria;
import com.itau.sg2.custodiaposvenda.domain.auditoria.SituacaoAuditoria;
import com.itau.sg2.custodiaposvenda.domain.pedido.PedidoEvent;
import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.function.Supplier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * O foco aqui é a <b>ordem</b> das operações de idempotência. É a única coisa que separa
 * "não duplica" de "some sem deixar rastro", e não dá para ver isso lendo o código de uma vez.
 */
class ProcessarPedidoFacadeTest {

    static class IdempotenciaFake implements IdempotenciaPort {
        final Set<String> marcadas = new HashSet<>();
        final List<String> operacoes = new ArrayList<>();

        @Override public boolean tentarIniciar(String chave) {
            operacoes.add("iniciar:" + chave);
            return marcadas.add(chave);
        }

        @Override public void concluir(String chave) { operacoes.add("concluir:" + chave); }

        @Override public void liberar(String chave) {
            operacoes.add("liberar:" + chave);
            marcadas.remove(chave);
        }
    }

    static class AuditoriaFake implements AuditoriaPort {
        final List<SituacaoAuditoria> situacoes = new ArrayList<>();
        int drenagens = 0;

        @Override public void iniciar(Long idOperacao) { }

        @Override public void registrar(Supplier<ParametrosAuditoria> p) {
            situacoes.add(p.get().situacao());
        }

        @Override public List<EventoAuditoria> drenar() { drenagens++; return List.of(); }
    }

    static class MetricasFake implements MetricasPort {
        final List<String> status = new ArrayList<>();

        @Override public void incrementarContador(String nome, String... tags) {
            for (int i = 0; i < tags.length - 1; i += 2) {
                if (TAG_STATUS.equals(tags[i])) status.add(tags[i + 1]);
            }
        }

        @Override public void registrarTempo(String nome, Runnable acao, String... tags) { acao.run(); }
    }

    /** Executa na hora: o teste não deve depender de agendamento. */
    private static final ExecutorAssincronoPort EXECUTOR_DIRETO = Runnable::run;

    private static final PublicadorAuditoriaPort AUDITORIA_NOOP = new PublicadorAuditoriaPort() {
        @Override public <T> void publicar(List<T> eventos) { }
    };

    private ProcessarPedidoFacade facade(ProcessarPedidoUseCasePort useCase,
                                         IdempotenciaFake idem,
                                         AuditoriaFake auditoria,
                                         MetricasFake metricas) {
        return new ProcessarPedidoFacade(useCase, AUDITORIA_NOOP, auditoria,
                EXECUTOR_DIRETO, metricas, idem);
    }

    @Test
    @DisplayName("sucesso: inicia antes e conclui DEPOIS do caso de uso")
    void concluiDepoisDoProcessamento() {
        var idem = new IdempotenciaFake();
        var auditoria = new AuditoriaFake();
        var metricas = new MetricasFake();
        var ordem = new ArrayList<String>();

        ProcessarPedidoUseCasePort useCase = event -> ordem.add("processou");

        var facadeInstrumentada = new ProcessarPedidoFacade(
                e -> { ordem.add("processou"); }, AUDITORIA_NOOP, auditoria, EXECUTOR_DIRETO, metricas,
                new IdempotenciaPort() {
                    @Override public boolean tentarIniciar(String c) { ordem.add("iniciar"); return true; }
                    @Override public void concluir(String c) { ordem.add("concluir"); }
                    @Override public void liberar(String c) { ordem.add("liberar"); }
                });

        facadeInstrumentada.executar(new PedidoEvent(1L, Fluxo.PUBLICA_SQS));

        assertEquals(List.of("iniciar", "processou", "concluir"), ordem,
                "concluir antes de processar deixaria a chave marcada mesmo em caso de falha");
        assertEquals(List.of(MetricasPort.STATUS_SUCESSO), metricas.status);
        assertTrue(useCase != null);
    }

    @Test
    @DisplayName("duplicata é descartada sem processar e sem auditoria")
    void duplicataNaoProcessa() {
        var idem = new IdempotenciaFake();
        var auditoria = new AuditoriaFake();
        var metricas = new MetricasFake();
        var processamentos = new ArrayList<Long>();

        var facade = facade(e -> processamentos.add(e.idOperacao()), idem, auditoria, metricas);
        var event = new PedidoEvent(5L, Fluxo.PUBLICA_SQS);

        facade.executar(event);
        facade.executar(event);

        assertEquals(1, processamentos.size(), "a segunda entrega não pode ser processada");
        assertEquals(List.of(MetricasPort.STATUS_SUCESSO, MetricasPort.STATUS_DUPLICADO), metricas.status);
        assertEquals(1, auditoria.drenagens, "duplicata não abre contexto de auditoria");
    }

    @Test
    @DisplayName("falha LIBERA a chave — senão a reentrega some como falsa duplicata")
    void falhaLiberaChave() {
        var idem = new IdempotenciaFake();
        var metricas = new MetricasFake();

        var facade = facade(e -> { throw new IllegalStateException("falhou"); },
                idem, new AuditoriaFake(), metricas);

        assertThrows(IllegalStateException.class,
                () -> facade.executar(new PedidoEvent(9L, Fluxo.PUBLICA_SQS)));

        assertTrue(idem.operacoes.contains("liberar:pedido#9#PUBLICA_SQS"),
                "sem liberar, a reentrega seria descartada como duplicata: " + idem.operacoes);
        assertFalse(idem.marcadas.contains("pedido#9#PUBLICA_SQS"));
        assertEquals(List.of(MetricasPort.STATUS_ERRO), metricas.status);
    }

    @Test
    @DisplayName("depois de falhar, a reentrega é processada normalmente")
    void reentregaAposFalhaFunciona() {
        var idem = new IdempotenciaFake();
        var tentativas = new ArrayList<Long>();

        var facade = facade(e -> {
            tentativas.add(e.idOperacao());
            if (tentativas.size() == 1) throw new IllegalStateException("primeira falha");
        }, idem, new AuditoriaFake(), new MetricasFake());

        var event = new PedidoEvent(3L, Fluxo.PUBLICA_SQS);
        assertThrows(IllegalStateException.class, () -> facade.executar(event));
        facade.executar(event);

        assertEquals(2, tentativas.size(), "a reentrega precisa passar pelo processamento");
    }

    @Test
    @DisplayName("a chave separa fluxos diferentes da mesma operação")
    void chaveIncluiFluxo() {
        var idem = new IdempotenciaFake();
        var processamentos = new ArrayList<Fluxo>();

        var facade = facade(e -> processamentos.add(e.fluxo()), idem, new AuditoriaFake(), new MetricasFake());

        facade.executar(new PedidoEvent(1L, Fluxo.PUBLICA_SQS));
        facade.executar(new PedidoEvent(1L, Fluxo.DEMOCRATIZAR_FIREHOSE_BATCH));

        assertEquals(2, processamentos.size(),
                "mesmo id em fluxos diferentes não é duplicata");
    }

    @Test
    @DisplayName("a auditoria é drenada mesmo quando o processamento falha")
    void drenaAuditoriaEmFalha() {
        var auditoria = new AuditoriaFake();

        var facade = facade(e -> { throw new IllegalStateException("falhou"); },
                new IdempotenciaFake(), auditoria, new MetricasFake());

        assertThrows(IllegalStateException.class,
                () -> facade.executar(new PedidoEvent(1L, Fluxo.PUBLICA_SQS)));

        assertEquals(1, auditoria.drenagens, "o finally precisa drenar em qualquer caminho");
        assertEquals(List.of(SituacaoAuditoria.EVENTO_RECEBIDO, SituacaoAuditoria.EVENTO_PROCESSADO_ERRO),
                auditoria.situacoes);
    }
}
