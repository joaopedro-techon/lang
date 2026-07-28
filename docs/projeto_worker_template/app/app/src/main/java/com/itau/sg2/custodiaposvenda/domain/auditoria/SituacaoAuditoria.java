package com.itau.sg2.custodiaposvenda.domain.auditoria;

/**
 * Situações registradas na trilha de auditoria.
 * <p>
 * {@code EVENTO_EM_PROCESSAMENTO} foi removido: nenhum ponto do fluxo o emitia. Uma constante que
 * ninguém produz vira ruído para quem consulta a trilha, porque sugere um estado que nunca
 * aparece nos dados.
 */
public enum SituacaoAuditoria {
    EVENTO_RECEBIDO,
    EVENTO_PROCESSADO_SUCESSO,
    EVENTO_PROCESSADO_ERRO
}
