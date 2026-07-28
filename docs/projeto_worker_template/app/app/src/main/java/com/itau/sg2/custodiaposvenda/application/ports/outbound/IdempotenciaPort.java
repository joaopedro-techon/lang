package com.itau.sg2.custodiaposvenda.application.ports.outbound;

/**
 * Controle de reprocessamento.
 * <p>
 * O SQS entrega <b>ao menos uma vez</b>. Duplicata não é caso raro: acontece sempre que o
 * visibility timeout expira antes de a aplicação confirmar, quando a task é reciclada no meio do
 * processamento, ou quando o próprio SQS reentrega por conta própria. Sem este controle, cada
 * duplicata vira uma publicação duplicada no destino.
 * <p>
 * O protocolo tem três passos de propósito, e não apenas um "já vi esta chave?":
 * <ul>
 *   <li>{@link #tentarIniciar} marca a chave <i>antes</i> do processamento;</li>
 *   <li>{@link #concluir} promove a marca para definitiva <i>depois</i> do sucesso;</li>
 *   <li>{@link #liberar} remove a marca quando o processamento falha.</li>
 * </ul>
 * O passo de liberar é o que impede o modo de falha mais perigoso: marcar antes e falhar depois
 * faria a reentrega ser descartada como "duplicata", e a mensagem sumiria em silêncio — sem ir
 * para a DLQ, sem log de erro, sem métrica. Perda de dado disfarçada de idempotência.
 */
public interface IdempotenciaPort {

    /**
     * @return {@code true} se esta é a primeira vez que a chave aparece e o processamento deve
     *         seguir; {@code false} se já foi processada ou está em andamento em outra thread/task.
     */
    boolean tentarIniciar(String chave);

    void concluir(String chave);

    void liberar(String chave);
}
