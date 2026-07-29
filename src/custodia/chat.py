"""O modo conversa: onde o desenvolvedor fala com o Custod.IA.

Este arquivo e a ponte entre o REPL (`cli.py`) e o agente ReAct (`graph.py`).
Ele guarda duas coisas que o REPL sozinho nao teria:

1. O HISTORICO da conversa. O grafo e stateless entre chamadas: quem lembra do
   que ja foi dito somos nos, reenviando a lista de mensagens a cada turno.
2. A RENDERIZACAO do que o agente esta fazendo. Em vez de esperar em silencio
   ate a resposta final, usamos `stream()` para mostrar cada chamada de
   ferramenta na hora -- e o dev enxerga o agente lendo o projeto.

O grafo so e construido no PRIMEIRO turno (`_garantir_grafo`). Isso mantem o
/initialize e o /status funcionando sem chave da Anthropic: quem precisa de LLM
e a conversa, nao o wizard.
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import HumanMessage
from rich.markdown import Markdown
from rich.markup import escape
from rich.padding import Padding

from . import NOME
from .graph import build_graph
from .ui import console

# Quanto do retorno de uma ferramenta aparece na tela. O modelo recebe tudo;
# isto e so para o humano acompanhar sem afogar o terminal.
_PREVIA_RESULTADO = 120

# Prefixos que o proprio `tools.py` usa para sinalizar que algo deu errado.
_PREFIXOS_DE_FALHA = ("ERRO", "CANCELADO")


class ChatIndisponivel(RuntimeError):
    """O agente nao pode ser iniciado (falta de chave, por exemplo)."""


class Conversa:
    """Uma sessao de conversa: historico + grafo, vivos enquanto o REPL viver."""

    def __init__(self) -> None:
        self._grafo: Any = None
        self._mensagens: list[Any] = []

    # -- ciclo de vida -----------------------------------------------------

    def _garantir_grafo(self) -> Any:
        """Constroi o grafo na primeira vez que alguem realmente conversa."""
        if self._grafo is not None:
            return self._grafo

        if not os.getenv("ANTHROPIC_API_KEY"):
            raise ChatIndisponivel(
                "ANTHROPIC_API_KEY nao definida.\n"
                "Copie o .env.example para .env e preencha a chave "
                "(https://console.anthropic.com/settings/keys)."
            )
        try:
            self._grafo = build_graph()
        except Exception as exc:  # erro de credencial/config na montagem
            raise ChatIndisponivel(f"nao foi possivel iniciar o agente: {exc}") from exc
        return self._grafo

    def limpar(self) -> None:
        """Esquece o historico. O grafo (e a conexao) continuam de pe."""
        self._mensagens = []

    @property
    def vazia(self) -> bool:
        return not self._mensagens

    # -- um turno ----------------------------------------------------------

    def perguntar(self, texto: str) -> None:
        """Manda uma mensagem e vai imprimindo o que o agente faz e responde.

        Nao devolve nada: a saida ja foi para a tela. Erros de rede/API viram
        mensagem impressa em vez de excecao -- um turno que falha nao derruba a
        sessao nem apaga o historico.
        """
        grafo = self._garantir_grafo()

        # So confirmamos o historico se o turno inteiro der certo. Assim uma
        # chamada que estourou no meio nao deixa a conversa em estado quebrado.
        entrada = [*self._mensagens, HumanMessage(content=texto)]
        ja_exibidas = len(entrada)
        final = entrada

        # O spinner so gira enquanto esperamos o MODELO. Antes do no de
        # ferramentas ele e desligado de proposito: `write_file` e `run_maven`
        # podem parar para pedir aprovacao, e animacao por cima de um input()
        # embaralha a tela.
        pensando = console.status("[dim]pensando...[/dim]", spinner="dots")
        pensando.start()
        try:
            for estado in grafo.stream({"messages": entrada}, stream_mode="values"):
                pensando.stop()
                mensagens = estado["messages"]
                for mensagem in mensagens[ja_exibidas:]:
                    _renderizar(mensagem)
                ja_exibidas = len(mensagens)
                final = mensagens
                if not _vai_chamar_ferramenta(mensagens):
                    pensando.start()
        except KeyboardInterrupt:
            console.print("\n[yellow]  (interrompido -- o historico ate aqui foi mantido)[/yellow]")
            return
        except Exception as exc:
            console.print(f"\n[red]  Erro ao falar com o modelo:[/red] {escape(str(exc))}\n")
            return
        finally:
            pensando.stop()

        self._mensagens = list(final)


# ---------------------------------------------------------------------------
# Renderizacao das mensagens
# ---------------------------------------------------------------------------

def _vai_chamar_ferramenta(mensagens: list[Any]) -> bool:
    """O agente acabou de pedir uma ferramenta? Entao o proximo passo executa."""
    if not mensagens:
        return False
    ultima = mensagens[-1]
    return getattr(ultima, "type", "") == "ai" and bool(getattr(ultima, "tool_calls", None))


def _renderizar(mensagem: Any) -> None:
    """Mostra uma mensagem nova do grafo (do agente ou de uma ferramenta)."""
    tipo = getattr(mensagem, "type", "")

    if tipo == "tool":
        _renderizar_resultado(mensagem)
        return

    if tipo == "ai":
        texto = _texto(mensagem).strip()
        chamadas = getattr(mensagem, "tool_calls", None) or []
        if texto or chamadas:
            console.print()  # respiro antes de cada fala do agente
        if texto:
            console.print(f"[bold cyan]{NOME}[/bold cyan]")
            # O modelo responde em Markdown; renderizar de verdade e o que
            # transforma **negrito** e blocos de codigo em algo legivel.
            console.print(Padding(Markdown(texto), (0, 0, 0, 2)))
        for chamada in chamadas:
            nome = escape(str(chamada.get("name", "?")))
            args = _argumentos(chamada.get("args"))
            console.print(
                f"  [green]●[/green] [bold]{nome}[/bold]"
                + (f"  [dim]{args}[/dim]" if args else "")
            )


def _renderizar_resultado(mensagem: Any) -> None:
    """Uma linha discreta com o que a ferramenta devolveu."""
    conteudo = _texto(mensagem).strip()
    if not conteudo:
        return
    primeira = conteudo.splitlines()[0]
    if len(primeira) > _PREVIA_RESULTADO:
        primeira = primeira[:_PREVIA_RESULTADO] + "..."
    extras = conteudo.count("\n")
    sufixo = f" (+{extras} linhas)" if extras else ""

    falhou = conteudo.startswith(_PREFIXOS_DE_FALHA)
    cor = "red" if falhou else "dim"
    console.print(f"    [dim]└[/dim] [{cor}]{escape(primeira + sufixo)}[/{cor}]")


def _texto(mensagem: Any) -> str:
    """Extrai o texto de uma mensagem.

    O `content` da Anthropic pode vir como string OU como lista de blocos
    (texto, tool_use, thinking...). Aqui juntamos so os blocos de texto.
    """
    conteudo = getattr(mensagem, "content", "")
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        partes = []
        for bloco in conteudo:
            if isinstance(bloco, str):
                partes.append(bloco)
            elif isinstance(bloco, dict) and bloco.get("type") == "text":
                partes.append(bloco.get("text", ""))
        return "".join(partes)
    return str(conteudo)


def _argumentos(args: Any) -> str:
    """Resume os argumentos de uma chamada de ferramenta em uma linha.

    Escapa o resultado: conteudo de arquivo com colchetes viraria markup do
    rich e quebraria (ou sumiria d)a tela.
    """
    if not isinstance(args, dict) or not args:
        return ""
    partes = []
    for chave, valor in args.items():
        texto = str(valor).replace("\n", " ")
        if len(texto) > 40:
            texto = texto[:40] + "..."
        partes.append(f"{chave}={texto}")
    return escape(", ".join(partes))


# ---------------------------------------------------------------------------
# O sub-loop do /chat
# ---------------------------------------------------------------------------

def loop_de_conversa(conversa: Conversa) -> None:
    """Fica conversando ate o dev sair. Chamado pelo comando /chat.

    Fora daqui, o REPL tambem manda texto solto direto para `perguntar()` --
    os dois caminhos compartilham a MESMA `Conversa`, entao o historico
    continua o mesmo entre um jeito e outro.
    """
    console.print()
    console.rule("[bold cyan]modo conversa[/bold cyan]", style="cyan")
    console.print(
        "[dim]Pergunte, ou peca uma alteracao no codigo.[/dim]\n"
        "  [bold]/sair[/bold]    [dim]volta para os comandos (ou Ctrl+D)[/dim]\n"
        "  [bold]/limpar[/bold]  [dim]esquece a conversa ate aqui[/dim]"
    )

    while True:
        try:
            entrada = console.input("\n[bold]voce[/bold][cyan]>[/cyan] ").lstrip("﻿").strip()
        except EOFError:
            console.print()
            return
        except KeyboardInterrupt:
            console.print("\n[dim](use /sair para voltar)[/dim]")
            continue

        if not entrada:
            continue
        comando = entrada.lower()
        if comando in ("/sair", "/exit", "/quit", "/voltar"):
            console.rule(style="dim")
            return
        if comando in ("/limpar", "/reset"):
            conversa.limpar()
            console.print("[dim]  (historico limpo)[/dim]")
            continue

        try:
            conversa.perguntar(entrada)
        except ChatIndisponivel as exc:
            console.print(f"\n[yellow]  {escape(str(exc))}[/yellow]\n")
            return
