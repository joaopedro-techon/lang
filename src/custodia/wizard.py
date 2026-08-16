"""Pecas comuns aos wizards deterministicos do /infra.

O /infra tem dois ramos -- worker e echobridge -- e eles fazem exatamente a
mesma coisa em tres pontos. Manter isso em um lugar so evita a pior classe de
bug destes wizards: dois ramos que discordam sobre o que e uma resposta valida
ou sobre o que fazer quando a AWS nao responde.

1. `perguntar()`  -- a UNICA forma de um no pausar o grafo e receber resposta,
   sempre passando pelo `validate()` do catalogo de perguntas;
2. `escolher_ou_digitar()` -- a degradacao para campo de texto quando a AWS nao
   listou nada (conta nova, ou perfil sem permissao de listar);
3. `com_aws()` -- traduz uma falha de consulta em fim de fluxo legivel, em vez
   de deixar a excecao subir no meio do wizard.

Os STATUS moram aqui pelo mesmo motivo: quem le o estado final (a CLI) compara
com estas constantes, seja qual for o ramo que produziu o resultado.
"""

from __future__ import annotations

from typing import Any, Callable

from langgraph.types import interrupt

from . import aws
from .questions import Option, Question, validate

STATUS_BLOQUEADO = "blocked"
STATUS_CANCELADO = "cancelled"
STATUS_ESCRITO = "written"
STATUS_ERRO_AWS = "aws_error"

# Valor reservado da opcao "nao esta na lista, quero digitar". Comeca e termina
# com "__" para nunca colidir com um ARN, um nome de cluster ou um hostname.
VALOR_OUTRO = "__outro__"


def perguntar(pergunta: Question) -> Any:
    """Pausa o grafo, entrega a pergunta ao frontend e valida o que voltou."""
    resposta = interrupt(pergunta.to_dict())
    return validate(pergunta, resposta)


def escolher_ou_digitar(
    id_pergunta: str,
    titulo: str,
    opcoes: list[Option],
    ajuda: str = "",
    vazio: str = "",
) -> Question:
    """Vira uma lista quando a AWS devolveu opcoes; um campo de texto quando nao.

    A consulta pode voltar vazia por motivo legitimo -- conta nova, ou o perfil
    sem permissao de listar. Travar o wizard nesse caso seria pior do que
    deixar o dev digitar o valor que ele ja conhece.
    """
    if opcoes:
        return Question(
            id=id_pergunta, kind="choice", title=titulo, help=ajuda, options=tuple(opcoes)
        )
    return Question(
        id=id_pergunta,
        kind="text",
        title=titulo,
        help=(ajuda + "\n" + vazio).strip(),
    )


def com_escape(opcoes: list[Option], rotulo: str = "Nao esta na lista -- quero digitar") -> list[Option]:
    """Acrescenta a saida de emergencia ao fim de uma lista vinda da AWS.

    Diferente de `escolher_ou_digitar`, que so degrada quando a lista veio
    VAZIA, isto cobre o caso em que a lista veio cheia mas o valor certo nao
    esta nela -- um topico SNS criado em outra conta, um broker Kafka que nao e
    recurso da AWS. Sem esta opcao o dev ficaria preso escolhendo o item errado.
    """
    return [*opcoes, Option(VALOR_OUTRO, rotulo, "Abre um campo de texto livre.")]


def com_aws(ambiente: str, tarefa: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    """Roda uma consulta na AWS traduzindo a falha em fim de fluxo legivel."""
    perfil = aws.perfil_do_ambiente(ambiente)
    try:
        return tarefa(perfil)
    except aws.AwsIndisponivel as exc:
        return {"status": STATUS_ERRO_AWS, "message": str(exc)}


def rota_aws(state: dict[str, Any]) -> str:
    return "parar" if state.get("status") == STATUS_ERRO_AWS else "continuar"


def rota_cancelamento(state: dict[str, Any]) -> str:
    return "parar" if state.get("status") == STATUS_CANCELADO else "continuar"
