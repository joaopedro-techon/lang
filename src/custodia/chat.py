"""O modo conversa: onde o desenvolvedor fala com o Custod.IA.

Este arquivo e a ponte entre o REPL (`cli.py`) e o agente ReAct (`graph.py`).
Ele guarda duas coisas que o REPL sozinho nao teria:

1. O HISTORICO da conversa. O grafo e stateless entre chamadas: quem lembra do
   que ja foi dito somos nos, reenviando a lista de mensagens a cada turno.
2. A RENDERIZACAO do que o agente esta fazendo. Em vez de esperar em silencio
   ate a resposta final, usamos `stream()` para mostrar cada chamada de
   ferramenta na hora -- e o dev enxerga o agente lendo o projeto.

O grafo so e construido no PRIMEIRO turno (`_garantir_grafo`). Isso mantem o
/initialize e o /status funcionando sem credencial de LLM nenhuma: quem precisa
de modelo e a conversa, nao o wizard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage
from rich.markdown import Markdown
from rich.markup import escape
from rich.padding import Padding

from . import NOME
from .graph import build_graph
from .llm import LLMIndisponivel, verificar_credenciais
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
        # Gasto acumulado da sessao inteira. Fica FORA do historico de
        # proposito: o /limpar esquece a conversa, mas os tokens ja foram
        # cobrados -- zerar aqui seria mentir sobre o custo.
        self.uso_da_sessao = Uso()

    # -- ciclo de vida -----------------------------------------------------

    def _garantir_grafo(self) -> Any:
        """Constroi o grafo na primeira vez que alguem realmente conversa."""
        if self._grafo is not None:
            return self._grafo

        # Qual credencial falta depende do provedor escolhido no .env, entao
        # quem responde isso e o `llm.py` -- aqui so repassamos a mensagem.
        try:
            faltando = verificar_credenciais()
        except LLMIndisponivel as exc:  # AGENT_PROVIDER invalido
            raise ChatIndisponivel(str(exc)) from exc
        if faltando:
            raise ChatIndisponivel(faltando)

        try:
            self._grafo = build_graph()
        except LLMIndisponivel as exc:
            # Ja vem com mensagem acionavel (pacote faltando, modelo recusado).
            raise ChatIndisponivel(str(exc)) from exc
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
        do_turno = Uso()

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
                    # Somado aqui, e nao no fim: um turno interrompido no meio
                    # tambem gastou, e o total da sessao tem que refletir isso.
                    parcial = _uso_da_mensagem(mensagem)
                    if parcial is not None:
                        do_turno += parcial
                        self.uso_da_sessao += parcial
                ja_exibidas = len(mensagens)
                final = mensagens
                if not _vai_chamar_ferramenta(mensagens):
                    pensando.start()
        except KeyboardInterrupt:
            console.print("\n[yellow]  (interrompido -- o historico ate aqui foi mantido)[/yellow]")
            return
        except Exception as exc:
            console.print(f"\n[red]  Erro ao falar com o modelo:[/red] {_explicar_erro(exc)}\n")
            return
        finally:
            # No `finally` para o total sair tambem quando o turno falha ou e
            # interrompido -- justamente os casos em que dai vontade de saber
            # quanto ja tinha sido gasto.
            pensando.stop()
            _renderizar_total_do_turno(do_turno)

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
        # O custo desta volta do loop, antes das ferramentas que ela pediu:
        # assim a chamada e o resultado dela seguem visualmente colados, e da
        # para ver o prompt engordando a cada volta.
        uso = _uso_da_mensagem(mensagem)
        if uso is not None:
            detalhe = f"{_milhar(uso.entrada)} entrada"
            if uso.cache:
                detalhe += f" ({_milhar(uso.cache)} do cache)"
            detalhe += f" · {_milhar(uso.saida)} saida"
            console.print(f"  [dim]· {detalhe}[/dim]")
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


# Falhas que sao do PROVEDOR, nao do que mandamos: o SDK ja repetiu
# AGENT_MAX_RETRIES vezes com backoff antes de chegar aqui, entao ver uma
# destas significa que o problema durou mais que a janela de retentativa.
_STATUS_TRANSITORIO = {
    429: "limite de requisicoes do provedor atingido",
    500: "erro interno do provedor",
    502: "gateway do provedor com problema",
    503: "provedor indisponivel no momento",
    529: "provedor sobrecarregado",
}


def _explicar_erro(exc: Exception) -> str:
    """Traduz falha conhecida do provedor; o que nao reconhecemos vai cru.

    O `status_code` e lido por duck typing de proposito: os SDKs da Anthropic
    e da OpenAI expoem esse atributo nas excecoes de HTTP, e assim a traducao
    funciona nos dois sem este arquivo importar nenhum dos dois.
    """
    motivo = _STATUS_TRANSITORIO.get(getattr(exc, "status_code", None))
    if motivo is None:
        return escape(str(exc))
    return (
        f"{motivo}.\n"
        "  E do lado do provedor, nao da sua pergunta -- o SDK ja repetiu a\n"
        "  chamada sozinho e nao adiantou. Espere um pouco e mande de novo: a\n"
        "  conversa anterior foi mantida, so esta pergunta nao entrou no\n"
        "  historico."
    )


def _milhar(valor: int) -> str:
    """1234 -> '1.2k'. So para caber numa linha discreta."""
    return f"{valor / 1000:.1f}k" if valor >= 1000 else str(valor)


@dataclass
class Uso:
    """Tokens gastos: uma chamada ao modelo, um turno ou a sessao inteira.

    Sao os tres niveis que interessam, e a mesma estrutura serve para todos --
    somar dois `Uso` sobe de nivel. `chamadas` importa porque no loop ReAct um
    unico turno vira varias idas ao modelo, e e isso que explica a conta.
    """

    chamadas: int = 0
    entrada: int = 0
    cache: int = 0
    saida: int = 0

    def __iadd__(self, outro: "Uso") -> "Uso":
        self.chamadas += outro.chamadas
        self.entrada += outro.entrada
        self.cache += outro.cache
        self.saida += outro.saida
        return self

    @property
    def houve_chamada(self) -> bool:
        return self.chamadas > 0

    def resumo(self) -> str:
        """Uma linha com o gasto. Sem markup: quem imprime decide o estilo."""
        if not self.houve_chamada:
            return "0 -- nenhuma chamada ao modelo"
        entrada = f"{_milhar(self.entrada)} entrada"
        # O cache vai entre parenteses porque e uma PARTE da entrada, nao uma
        # parcela a mais -- separado por "·" alguem soma os dois e reporta
        # errado. E so aparece quando houve: provedor que nao reporta cache
        # mostraria "0 do cache" e pareceria defeito, nao ausencia de dado.
        if self.cache:
            entrada += f" ({_milhar(self.cache)} do cache)"
        chamadas = "1 chamada" if self.chamadas == 1 else f"{self.chamadas} chamadas"
        return f"{chamadas} · {entrada} · {_milhar(self.saida)} saida"


def _uso_da_mensagem(mensagem: Any) -> Uso | None:
    """Extrai o gasto de UMA resposta do modelo. None se o provedor nao reporta."""
    bruto = getattr(mensagem, "usage_metadata", None)
    if not bruto:
        return None
    detalhes = bruto.get("input_token_details") or {}
    return Uso(
        chamadas=1,
        entrada=bruto.get("input_tokens", 0),
        cache=detalhes.get("cache_read", 0),
        saida=bruto.get("output_tokens", 0),
    )


def _renderizar_total_do_turno(uso: Uso) -> None:
    """Fecha o turno com o total. Silencioso se o modelo nem foi chamado."""
    if not uso.houve_chamada:
        return
    console.print(f"\n  [dim]total do turno: {uso.resumo()}[/dim]")


def _texto(mensagem: Any) -> str:
    """Extrai o texto de uma mensagem.

    O `content` varia por provedor: a OpenAI manda uma string simples, a
    Anthropic manda uma lista de blocos (texto, tool_use, thinking...). Tratar
    os dois casos e o que deixa a renderizacao funcionar com qualquer LLM.
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
