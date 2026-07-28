package com.itau.sg2.custodiaposvenda.application.ports.outbound;

import com.itau.sg2.custodiaposvenda.domain.pedido.Pedido;
import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;

/**
 * Publica o pedido no destino do seu fluxo.
 * <p>
 * A sobrecarga {@code publicar(List<Pedido>)} foi removida. Ela tinha um defeito difícil de ver:
 * a interface trazia um {@code default} que iterava a lista chamando {@code publicar(Pedido)},
 * enquanto o {@code FirehoseBatchPublicador} sobrescrevia na <b>direção oposta</b>, fazendo
 * {@code publicar(Pedido)} delegar para {@code publicar(List.of(pedido))}. Qualquer chamada
 * atravessava a outra sobrecarga, e nenhuma das duas era a implementação "de verdade".
 * <p>
 * Nada no fluxo chegava a usá-la: o consumo é mensagem a mensagem. O agrupamento real acontece
 * dentro do cliente do Firehose, que particiona os registros conforme os limites do
 * {@code PutRecordBatch}.
 */
public interface PublicadorMensagemPort {

    Fluxo fluxoSuportado();

    void publicar(Pedido pedido);
}
