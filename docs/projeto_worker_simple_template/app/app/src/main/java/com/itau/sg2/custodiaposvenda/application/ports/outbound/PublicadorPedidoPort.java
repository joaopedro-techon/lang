package com.itau.sg2.custodiaposvenda.application.ports.outbound;

import com.itau.sg2.custodiaposvenda.domain.pedido.Pedido;
import com.itau.sg2.custodiaposvenda.domain.pedido.enums.Fluxo;

/**
 * Publica o pedido processado no destino do seu {@link Fluxo}.
 * <p>
 * É a <b>estratégia</b> do fluxo: há uma implementação por destino (SNS, SQS, Firehose) e o caso de
 * uso escolhe entre elas pelo campo {@code fluxo} da mensagem. Cada implementação declara o fluxo
 * que atende em {@link #fluxoSuportado()}, e o Spring injeta todas como uma {@code List} — adicionar
 * um destino novo é escrever uma classe, sem tocar no caso de uso nem em nenhum {@code switch}.
 * <p>
 * Só existe {@code publicar(Pedido)}, no singular: o consumo da fila é mensagem a mensagem, e uma
 * sobrecarga de lote sem chamador seria código que ninguém exercita.
 */
public interface PublicadorPedidoPort {

    Fluxo fluxoSuportado();

    void publicar(Pedido pedido);
}
