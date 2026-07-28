package com.itau.sg2.custodiaposvenda.shared.logging;

import com.fasterxml.jackson.annotation.JsonValue;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/**
 * Campo {@code Payload} do log, montado campo a campo.
 * <p>
 * Este tipo existe para tornar o vazamento de dado sensível <b>impossível por construção</b>, e não
 * uma questão de disciplina. Antes, o payload era {@code Object}: passar o objeto de domínio
 * inteiro era o caminho mais curto, e todo campo novo adicionado a ele — CPF, conta, nome, valor —
 * passava a ser logado em INFO automaticamente, sem ninguém decidir isso. Num template replicado
 * por um gerador, esse default é herdado por todo projeto derivado.
 * <p>
 * Aqui cada campo precisa ser nomeado explicitamente, então só vai para o log o que alguém
 * escolheu colocar. Campo que ninguém nomeou não vaza.
 * <p>
 * Prefira identificadores (ids, códigos, enums) a conteúdo. Quando um valor sensível for
 * realmente necessário para diagnóstico, <b>mascare antes</b> de colocá-lo aqui — este template
 * não embute máscaras porque a regra de mascaramento é política de cada domínio.
 *
 * <pre>{@code
 * Logger.info("Pedido processado",
 *         PayloadLog.de("idCliente", pedido.idCliente())
 *                   .e("idPedido", pedido.idPedido())
 *                   .e("situacao", pedido.situacao()));
 * }</pre>
 * <p>
 * Serializa como um objeto JSON simples ({@code @JsonValue}), sem o nível extra do wrapper.
 * {@code com.fasterxml.jackson.annotation} é comum ao Jackson 2 e ao 3 — logo esta classe não
 * depende da decisão pendente entre as duas versões.
 */
public final class PayloadLog {

    private final Map<String, Object> campos;

    private PayloadLog(Map<String, Object> campos) {
        this.campos = campos;
    }

    public static PayloadLog de(String chave, Object valor) {
        Map<String, Object> campos = new LinkedHashMap<>();
        campos.put(Objects.requireNonNull(chave, "chave não pode ser nula"), valor);
        return new PayloadLog(campos);
    }

    /** Retorna uma nova instância — {@code PayloadLog} é imutável. */
    public PayloadLog e(String chave, Object valor) {
        Map<String, Object> novos = new LinkedHashMap<>(campos);
        novos.put(Objects.requireNonNull(chave, "chave não pode ser nula"), valor);
        return new PayloadLog(novos);
    }

    @JsonValue
    public Map<String, Object> campos() {
        return Collections.unmodifiableMap(campos);
    }
}
