"""Renderizacao das perguntas no terminal.

Esta e a camada de FRONTEND do wizard. O grafo (`initialize.py`) nao sabe que
existe um terminal: ele so emite um JSON descrevendo a pergunta. Este arquivo
transforma esse JSON em texto na tela e converte o que o usuario digitou de
volta em um valor.

Divisao de responsabilidades:

- aqui  -> PARSING (entender "1,3" como duas opcoes, "s" como sim) e o loop
           de repergunta quando a entrada e invalida;
- questions.validate() -> a REGRA do que e valido.

O parsing e amigavel ao humano e pode mudar por frontend; a regra e unica e
compartilhada. Por isso este arquivo nunca decide sozinho se algo e valido:
ele sempre pergunta para `validate()`.
"""

from __future__ import annotations

import sys
from typing import Any

from .questions import Question, ValidationError, validate

LARGURA = 62

# Respostas aceitas em perguntas de sim/nao.
_SIM = {"s", "sim", "y", "yes"}
_NAO = {"n", "nao", "não", "no", ""}
# Formas de dizer "nenhuma" numa multi-escolha.
_NENHUMA = {"nenhuma", "nenhum", "none", "0", "-"}


class WizardAbortado(RuntimeError):
    """Usuario interrompeu o wizard (Ctrl+C ou fim da entrada)."""


def perguntar_no_terminal(payload: dict[str, Any]) -> Any:
    """Mostra a pergunta e devolve uma resposta ja validada.

    `payload` e o dict emitido pelo `interrupt()` do grafo. O loop so termina
    quando a resposta passa em `validate()` -- ou seja, o grafo nunca recebe
    entrada invalida vinda do terminal.
    """
    pergunta = Question.from_dict(payload)
    _renderizar_enunciado(pergunta)

    while True:
        bruto = _ler(_texto_do_prompt(pergunta))
        try:
            valor = _converter(pergunta, bruto)
            return validate(pergunta, valor)
        except ValidationError as exc:
            print(f"  ! {exc}")


# ---------------------------------------------------------------------------
# Saida
# ---------------------------------------------------------------------------

def _renderizar_enunciado(pergunta: Question) -> None:
    print()
    print("-" * LARGURA)
    print(pergunta.title)
    if pergunta.help:
        print()
        print(pergunta.help)
    if pergunta.options:
        print()
        for indice, opcao in enumerate(pergunta.options, start=1):
            marca = "" if opcao.available else "  (em breve)"
            print(f"  {indice}) {opcao.label}{marca}")
            if opcao.description:
                print(f"     {opcao.description}")
    print()


def _texto_do_prompt(pergunta: Question) -> str:
    if pergunta.kind == "choice":
        return f"Escolha [1-{len(pergunta.options)}]: "
    if pergunta.kind == "multi_choice":
        sufixo = " | vazio = nenhuma" if pergunta.allow_empty else ""
        return f"Escolha (ex.: 1,3{sufixo}): "
    if pergunta.kind == "confirm":
        return "Confirmar? [s/N]: "
    if pergunta.kind == "integer":
        faixa = ""
        if pergunta.min_value is not None and pergunta.max_value is not None:
            faixa = f" [{pergunta.min_value}-{pergunta.max_value}]"
        return f"Resposta{faixa}: "
    return "Resposta: "


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

def _ler(prompt: str) -> str:
    """Le uma linha. Ctrl+C ou fim da entrada abortam o wizard."""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        raise WizardAbortado("wizard interrompido pelo usuario") from None


def _converter(pergunta: Question, bruto: str) -> Any:
    """Converte o texto digitado no valor que `validate()` espera."""
    texto = bruto.strip()

    if pergunta.kind == "choice":
        return _converter_escolha(pergunta, texto)
    if pergunta.kind == "multi_choice":
        return _converter_multi_escolha(pergunta, texto)
    if pergunta.kind == "confirm":
        return _converter_confirmacao(texto)
    # "text" e "integer" seguem crus: validate() cuida de limpar e converter.
    return texto


def _converter_escolha(pergunta: Question, texto: str) -> Any:
    """Aceita o numero da lista ('2') ou o valor tecnico ('app')."""
    if not texto:
        raise ValidationError("Digite o numero da opcao desejada.")
    return _resolver_opcao(pergunta, texto)


def _converter_multi_escolha(pergunta: Question, texto: str) -> list[str]:
    """Aceita '1,3', '1 3', vazio ou 'nenhuma'."""
    if not texto or texto.lower() in _NENHUMA:
        return []
    partes = [p for p in texto.replace(",", " ").split() if p]
    return [_resolver_opcao(pergunta, parte) for parte in partes]


def _resolver_opcao(pergunta: Question, token: str) -> str:
    """Traduz um numero da lista para o valor da opcao correspondente."""
    if token.isdigit():
        indice = int(token)
        if not 1 <= indice <= len(pergunta.options):
            raise ValidationError(
                f"'{token}' esta fora da lista (use 1 a {len(pergunta.options)})."
            )
        return pergunta.options[indice - 1].value
    # Nao e numero: devolve como veio e deixa validate() julgar. Assim
    # digitar o valor tecnico ('sqs') tambem funciona.
    return token.lower()


def _converter_confirmacao(texto: str) -> bool:
    resposta = texto.lower()
    if resposta in _SIM:
        return True
    if resposta in _NAO:
        return False
    raise ValidationError("Responda 's' para sim ou 'n' para nao.")


# ---------------------------------------------------------------------------
# Utilidades de saida usadas pelo CLI
# ---------------------------------------------------------------------------

def configurar_saida_utf8() -> None:
    """Tenta colocar stdout/stderr em UTF-8.

    No Windows o terminal nem sempre esta em UTF-8, e acentos viram lixo ou
    estouram UnicodeEncodeError. `errors="replace"` garante que, no pior caso,
    perdemos um acento em vez de derrubar a CLI.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass  # ambiente sem suporte: segue com o encoding padrao


def titulo(texto: str) -> None:
    print()
    print("=" * LARGURA)
    print(texto)
    print("=" * LARGURA)
