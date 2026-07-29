"""A camada de terminal: o `console` compartilhado e o frontend do wizard.

O `console` (rich) definido aqui e o UNICO da aplicacao -- a conversa
(`chat.py`), o gate de aprovacao (`tools.py`) e o REPL (`cli.py`) usam este
mesmo objeto. Um Console so evita que animacao (spinner) e escrita normal
briguem pelo cursor.

O resto do arquivo e o FRONTEND do wizard. O grafo (`initialize.py`) nao sabe
que existe um terminal: ele so emite um JSON descrevendo a pergunta. Este
arquivo transforma esse JSON em texto na tela e converte o que o usuario
digitou de volta em um valor.

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

from rich.console import Console
from rich.markup import escape

from .questions import Question, ValidationError, validate

try:
    import questionary
except ImportError:  # pragma: no cover - ambiente sem a dependencia instalada
    # Sem questionary a CLI inteira continua de pe: o wizard so volta a ser
    # digitado. Melhor degradar do que derrubar /status e /chat junto.
    questionary = None

# O console compartilhado por toda a CLI. Fora de um terminal de verdade
# (pipe, CI) o rich detecta sozinho e desliga cor e animacao.
console = Console(highlight=False)

LARGURA = 62

# Tipos de pergunta que ganham navegacao por setas. "text" e "integer" nao
# entram: ali o usuario tem mesmo que digitar.
_TIPOS_NAVEGAVEIS = ("choice", "multi_choice", "confirm")

# Paleta do questionary alinhada com o ciano que o resto da CLI usa.
_ESTILO = (
    questionary.Style(
        [
            ("qmark", "fg:cyan bold"),
            ("question", "bold"),
            ("pointer", "fg:cyan bold"),
            ("highlighted", "fg:cyan bold"),
            ("selected", "fg:cyan"),
            ("instruction", "fg:#808080"),
            ("answer", "fg:cyan bold"),
        ]
    )
    if questionary is not None
    else None
)

# Respostas aceitas em perguntas de sim/nao.
_SIM = {"s", "sim", "y", "yes"}
_NAO = {"n", "nao", "não", "no", ""}
# Formas de dizer "nenhuma" numa multi-escolha.
_NENHUMA = {"nenhuma", "nenhum", "none", "0", "-"}


class WizardAbortado(RuntimeError):
    """Usuario interrompeu o wizard (Ctrl+C ou fim da entrada)."""


class _SemNavegacao(RuntimeError):
    """O terminal passou no isatty() mas nao aguenta a lista navegavel.

    Acontece de verdade no Windows fora do console nativo (Git Bash/mintty):
    o prompt_toolkit levanta NoConsoleScreenBufferError. Nao e erro do
    usuario nem motivo para derrubar o wizard -- e so voltar para o modo
    digitado.
    """


# Vira True na primeira falha de navegacao: se um terminal nao aguenta a
# lista, nao vai aguentar nas proximas perguntas -- nao insistimos.
_navegacao_quebrada = False


def perguntar_no_terminal(payload: dict[str, Any]) -> Any:
    """Mostra a pergunta e devolve uma resposta ja validada.

    `payload` e o dict emitido pelo `interrupt()` do grafo. Existem dois
    frontends para a mesma pergunta:

    - NAVEGADO (setas + enter), quando ha um terminal de verdade;
    - DIGITADO ("1,3"), quando a entrada vem de um pipe/CI ou o questionary
      nao esta instalado.

    Os dois terminam no mesmo `validate()`, entao o grafo nunca recebe entrada
    invalida -- venha ela de qual frontend for.
    """
    global _navegacao_quebrada

    pergunta = Question.from_dict(payload)

    if _pode_navegar(pergunta):
        try:
            return _perguntar_navegando(pergunta)
        except _SemNavegacao as exc:
            _navegacao_quebrada = True
            console.print(
                f"[dim]  (este terminal nao suporta a lista navegavel: "
                f"{escape(str(exc))} -- seguindo no modo digitado)[/dim]"
            )

    _renderizar_enunciado(pergunta)
    while True:
        bruto = _ler(_texto_do_prompt(pergunta))
        try:
            valor = _converter(pergunta, bruto)
            return validate(pergunta, valor)
        except ValidationError as exc:
            print(f"  ! {exc}")


# ---------------------------------------------------------------------------
# Frontend navegado (setas)
# ---------------------------------------------------------------------------

def _pode_navegar(pergunta: Question) -> bool:
    """Da para usar setas aqui?

    Exige questionary instalado, um terminal interativo dos DOIS lados (ler
    tecla e desenhar a lista) e um tipo de pergunta que faca sentido navegar.
    """
    if questionary is None or _navegacao_quebrada:
        return False
    if pergunta.kind not in _TIPOS_NAVEGAVEIS:
        return False
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def _perguntar_navegando(pergunta: Question) -> Any:
    """Pergunta com setas, repetindo enquanto `validate()` recusar.

    O caso real de repeticao e a multi-escolha obrigatoria: da para confirmar
    sem marcar nada, e ai a regra manda perguntar de novo.
    """
    console.print()
    if pergunta.help:
        console.print(f"[dim]{escape(pergunta.help)}[/dim]")

    while True:
        valor = _escolher(pergunta)
        try:
            return validate(pergunta, valor)
        except ValidationError as exc:
            console.print(f"  [red]![/red] {escape(str(exc))}")


def _escolher(pergunta: Question) -> Any:
    """Desenha a lista (ou o sim/nao) e devolve o valor bruto escolhido."""
    try:
        if pergunta.kind == "confirm":
            # default=False mantem a semantica do "[s/N]" digitado: enter = nao.
            return questionary.confirm(
                pergunta.title, default=False, style=_ESTILO, qmark="?"
            ).unsafe_ask()

        opcoes = [
            questionary.Choice(
                title=opcao.label + ("  (em breve)" if not opcao.available else ""),
                value=opcao.value,
                description=opcao.description or None,
            )
            for opcao in pergunta.options
        ]

        if pergunta.kind == "multi_choice":
            sufixo = " | nenhuma: so aperte enter" if pergunta.allow_empty else ""
            return questionary.checkbox(
                pergunta.title,
                choices=opcoes,
                style=_ESTILO,
                qmark="?",
                instruction=f"(setas movem, espaco marca, enter confirma{sufixo})",
            ).unsafe_ask()

        return questionary.select(
            pergunta.title,
            choices=opcoes,
            style=_ESTILO,
            qmark="?",
            instruction="(setas movem, enter confirma)",
        ).unsafe_ask()
    except (KeyboardInterrupt, EOFError):
        # Mesmo contrato do frontend digitado: Ctrl+C aborta o wizard inteiro.
        console.print()
        raise WizardAbortado("wizard interrompido pelo usuario") from None
    except Exception as exc:
        # O prompt_toolkit monta a tela ja na CHAMADA (nao no ask), e falha
        # em terminal Windows nao-nativo. Degradar para o modo digitado e
        # sempre melhor do que derrubar o /initialize.
        raise _SemNavegacao(type(exc).__name__) from exc


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
