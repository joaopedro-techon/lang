package com.itau.sg2.custodiaposvenda.application.ports.outbound;

/**
 * Publicação de métricas.
 * <p>
 * Antes a camada {@code application} chamava direto o {@code MetricsConfig} de
 * {@code infrastructure} — e recebia de volta um {@code io.micrometer...Timer}, deixando o
 * Micrometer vazar para dentro do caso de uso. A porta corta as duas coisas: a direção da
 * dependência e o tipo do fornecedor.
 * <p>
 * {@link #registrarTempo} recebe a ação em vez de devolver um cronômetro, justamente para que
 * nenhum tipo do Micrometer atravesse a fronteira.
 */
public interface MetricasPort {

    String TEMPO_PROCESSAMENTO = "custom.sg2.dogstatsd.app.pedido.processamento.duration";
    String PEDIDO_PROCESSADO = "custom.sg2.dogstatsd.app.pedido.count";

    /**
     * Falhas de entrega da fila. Métrica separada de {@link #PEDIDO_PROCESSADO} de propósito:
     * conta também o que nunca chega ao caso de uso (erro de conversão) e evita contabilizar a
     * mesma falha duas vezes.
     */
    String PEDIDO_FALHA = "custom.sg2.dogstatsd.app.pedido.falha.count";

    String TAG_FLUXO = "fluxo";
    String TAG_STATUS = "status";
    String TAG_TIPO_FALHA = "tipo";
    String TAG_EXCECAO = "excecao";

    String STATUS_SUCESSO = "sucesso";
    String STATUS_ERRO = "erro";
    /** Reentrega descartada pelo controle de idempotência. */
    String STATUS_DUPLICADO = "duplicado";

    /** Reentregar não resolve: a mensagem seguirá para a DLQ pela redrivePolicy da fila. */
    String TIPO_FALHA_PERMANENTE = "permanente";
    /** Pode passar numa próxima entrega (dependência indisponível, throttling, timeout). */
    String TIPO_FALHA_TRANSITORIA = "transitoria";

    void incrementarContador(String nome, String... tags);

    void registrarTempo(String nome, Runnable acao, String... tags);
}
