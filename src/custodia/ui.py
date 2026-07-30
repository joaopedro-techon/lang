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

from .questions import Option, Question, ValidationError, validate

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

# Respostas aceitas na pergunta de formato do modo guiado. Enter cai em
# "listar" porque e o comportamento que o wizard sempre teve.
_LISTAR = {"l", "listar", "lista", "1", ""}
_DIGITAR = {"d", "digitar", "digitado", "digite", "2"}


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


def perguntar_no_terminal(payload: dict[str, Any], guiado: bool = False) -> Any:
    """Mostra a pergunta e devolve uma resposta ja validada.

    `payload` e o dict emitido pelo `interrupt()` do grafo. Existem dois
    frontends para a mesma pergunta:

    - NAVEGADO (setas + enter), quando ha um terminal de verdade;
    - DIGITADO ("1,3"), quando a entrada vem de um pipe/CI ou o questionary
      nao esta instalado.

    Os dois terminam no mesmo `validate()`, entao o grafo nunca recebe entrada
    invalida -- venha ela de qual frontend for.

    `guiado=True` liga o modo do /config: em vez de o wizard DECIDIR o
    frontend, ele PERGUNTA antes de cada pergunta com opcoes ("listar ou
    digitar?"), e toda pergunta ganha um exemplo de resposta valida montado a
    partir das opcoes reais. O padrao e False para o /initialize e o /infra
    seguirem exatamente como eram.
    """
    global _navegacao_quebrada

    pergunta = Question.from_dict(payload)

    # No modo guiado quem responde escolhe o formato. So perguntamos quando ha
    # opcoes para listar (num sim/nao nao ha lista nenhuma) e quando existe
    # alguem de verdade do outro lado -- num pipe a pergunta extra comeria uma
    # linha da entrada e desalinharia todas as respostas seguintes.
    listar = True
    if guiado and pergunta.options and _entrada_interativa():
        listar = _perguntar_formato(pergunta)

    if listar and _pode_navegar(pergunta):
        try:
            return _perguntar_navegando(pergunta, guiado=guiado)
        except _SemNavegacao as exc:
            _navegacao_quebrada = True
            console.print(
                f"[dim]  (este terminal nao suporta a lista navegavel: "
                f"{escape(str(exc))} -- seguindo no modo digitado)[/dim]"
            )

    _renderizar_enunciado(pergunta, compacto=not listar)
    while True:
        bruto = _ler(_texto_do_prompt(pergunta, guiado=guiado))
        try:
            valor = _converter(pergunta, bruto)
            return validate(pergunta, valor)
        except ValidationError as exc:
            print(f"  ! {exc}")


# ---------------------------------------------------------------------------
# Modo guiado: o formato da resposta e os exemplos
# ---------------------------------------------------------------------------

def _perguntar_formato(pergunta: Question) -> bool:
    """Pergunta se e para listar as opcoes ou se a pessoa prefere digitar.

    Devolve True para listar. O titulo da pergunta vem junto de proposito:
    sem ele a escolha de formato apareceria sem contexto nenhum, e quem esta
    no meio do wizard nao saberia sobre o que esta decidindo.
    """
    console.print()
    console.print(f"[bold]{escape(pergunta.title)}[/bold]")
    while True:
        resposta = _ler(
            "  Listar as opcoes ou prefere digitar? [l/d] (enter = listar): "
        ).strip().lower()
        if resposta in _LISTAR:
            return True
        if resposta in _DIGITAR:
            return False
        print("  ! Responda 'l' para listar ou 'd' para digitar.")


def _exemplo_digitado(pergunta: Question) -> str:
    """Um exemplo de resposta valida, montado das opcoes REAIS da pergunta.

    Usa o `value` e nao o numero da linha: no modo digitado a lista numerada
    pode nem estar na tela (foi isso que a pessoa escolheu), e um exemplo que
    cita "2" sem mostrar a lista nao ajuda ninguem. O numero continua sendo
    aceito -- ver `_resolver_opcao`.
    """
    if pergunta.kind == "choice" and pergunta.options:
        # A segunda opcao quando existe: a primeira e o padrao obvio, e um
        # exemplo que repete o padrao nao ensina que da para escolher outra.
        opcao = pergunta.options[1] if len(pergunta.options) > 1 else pergunta.options[0]
        return f"ex.: {opcao.value}"
    if pergunta.kind == "multi_choice" and pergunta.options:
        escolhidas = _duas_opcoes(pergunta)
        exemplo = f"ex.: {','.join(o.value for o in escolhidas)}"
        if pergunta.allow_empty:
            exemplo += " | enter = nenhuma"
        return exemplo
    if pergunta.kind == "confirm":
        return "ex.: s para aplicar, enter para cancelar"
    if pergunta.kind == "integer" and pergunta.min_value is not None:
        return f"ex.: {pergunta.min_value}"
    return ""


def _exemplo_navegado(pergunta: Question) -> str:
    """O mesmo exemplo, na lingua do frontend de setas.

    "ex.: digite openai" seria mentira aqui: nesta tela nao se digita nada.
    """
    if pergunta.kind == "choice" and pergunta.options:
        opcao = pergunta.options[1] if len(pergunta.options) > 1 else pergunta.options[0]
        return f"ex.: desca ate '{opcao.label}' e aperte enter"
    if pergunta.kind == "multi_choice" and pergunta.options:
        escolhidas = _duas_opcoes(pergunta)
        rotulos = " e ".join(f"'{o.label}'" for o in escolhidas)
        exemplo = f"ex.: marque {rotulos} com espaco e aperte enter"
        if pergunta.allow_empty:
            exemplo += "; so enter = nenhuma"
        return exemplo
    if pergunta.kind == "confirm":
        return "ex.: y para aplicar, enter para cancelar"
    return ""


def _duas_opcoes(pergunta: Question) -> tuple[Option, ...]:
    """Duas opcoes para ilustrar uma multi-escolha, sem serem as duas vizinhas.

    Com tres ou mais pega a 1a e a 3a: um exemplo "1,2" sugere que so da para
    marcar opcoes seguidas.
    """
    if len(pergunta.options) >= 3:
        return pergunta.options[:3:2]
    return pergunta.options[:2]


def _entrada_interativa() -> bool:
    """Tem alguem digitando do outro lado, ou a entrada vem de um arquivo?"""
    try:
        return bool(sys.stdin.isatty())
    except (AttributeError, ValueError):
        return False


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


def _perguntar_navegando(pergunta: Question, guiado: bool = False) -> Any:
    """Pergunta com setas, repetindo enquanto `validate()` recusar.

    O caso real de repeticao e a multi-escolha obrigatoria: da para confirmar
    sem marcar nada, e ai a regra manda perguntar de novo.
    """
    console.print()
    if pergunta.help:
        console.print(f"[dim]{escape(pergunta.help)}[/dim]")
    if guiado:
        exemplo = _exemplo_navegado(pergunta)
        if exemplo:
            console.print(f"[dim]{escape(exemplo)}[/dim]")

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

def _renderizar_enunciado(pergunta: Question, compacto: bool = False) -> None:
    """Escreve a pergunta na tela antes de pedir a resposta digitada.

    `compacto=True` e para quem respondeu "prefiro digitar": desenhar a lista
    numerada logo depois disso seria ignorar a resposta. Mesmo assim as opcoes
    validas continuam na tela, em uma linha so -- sem elas nao daria para
    responder, e o que a pessoa recusou foi o MENU, nao o vocabulario.
    """
    if compacto:
        # O titulo ja saiu junto da pergunta de formato.
        print()
        if pergunta.help:
            print(pergunta.help)
        if pergunta.options:
            print(f"Opcoes: {', '.join(o.value for o in pergunta.options)}")
        print()
        return

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


def _texto_do_prompt(pergunta: Question, guiado: bool = False) -> str:
    if pergunta.kind == "choice":
        base = f"Escolha [1-{len(pergunta.options)}]"
    elif pergunta.kind == "multi_choice":
        sufixo = " | vazio = nenhuma" if pergunta.allow_empty else ""
        # No modo guiado este "ex.: 1,3" sai de cena: o exemplo vem do
        # `_exemplo_digitado`, e dois exemplos na mesma linha so confundem.
        base = "Escolha" if guiado else f"Escolha (ex.: 1,3{sufixo})"
    elif pergunta.kind == "confirm":
        base = "Confirmar? [s/N]"
    elif pergunta.kind == "integer":
        faixa = ""
        if pergunta.min_value is not None and pergunta.max_value is not None:
            faixa = f" [{pergunta.min_value}-{pergunta.max_value}]"
        base = f"Resposta{faixa}"
    else:
        base = "Resposta"

    if guiado:
        exemplo = _exemplo_digitado(pergunta)
        if exemplo:
            base = f"{base}  ({exemplo})"
    return f"{base}: "


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
