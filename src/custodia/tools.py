"""Ferramentas que o agente pode chamar.

Cada funcao decorada com @tool vira uma "ferramenta" que o modelo pode
invocar. A descricao (docstring) e o schema (type hints) sao lidos pelo
modelo para decidir QUANDO e COMO chamar cada uma.

Design: ferramentas dedicadas (em vez de um unico `bash`) dao ao harness
um ponto de controle tipado por acao -- ex.: podemos auditar/limitar a
escrita e o Maven separadamente da leitura.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from langchain_core.tools import tool
from rich.console import Group
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from .config import get_project_root, is_auto_approve, resolve_inside_project
from .conhecimento import KBIndisponivel, consultar
from .ui import console

# Limite para nao estourar o contexto do modelo com arquivos gigantes.
MAX_READ_CHARS = 60_000

# Quanto de cada trecho da base de conhecimento vai para o contexto. Trecho
# recuperado e o que mais infla o prompt: sem teto, uma consulta ampla come o
# orcamento do turno inteiro.
MAX_TRECHO_CHARS = 2_000

# Quantas linhas do conteudo aparecem na previa de aprovacao.
LINHAS_DE_PREVIA = 20

# Quantos nomes acompanham um erro de "caminho nao existe". O suficiente para o
# modelo se localizar, sem despejar uma pasta inteira no contexto.
MAX_ITENS_NA_DICA = 30


def _rotulo(caminho: Path) -> str:
    """O caminho como o modelo o escreveu: relativo a raiz, com barra normal."""
    root = get_project_root()
    if caminho == root:
        return "."
    return caminho.relative_to(root).as_posix()


def _pasta_existente_mais_proxima(alvo: Path) -> Path:
    """Sobe do alvo ate achar uma pasta que exista, sem passar da raiz."""
    root = get_project_root()
    atual = alvo
    while atual != root and root in atual.parents:
        if atual.is_dir():
            return atual
        atual = atual.parent
    return root


def _onde_procurar(alvo: Path) -> str:
    """O que EXISTE perto do caminho que nao existe.

    Sem isto, um caminho errado vira um beco sem saida: a ferramenta responde
    "nao existe" e o modelo, sem nenhuma informacao nova, tende a chutar de
    novo. Acontece direto nos repositorios da area, onde o projeto Maven mora
    em `app/` e o palpite natural de quem conhece Spring Boot -- `src` -- nao
    existe na raiz. Devolvendo a vizinhanca, ele se corrige no mesmo turno.
    """
    pasta = _pasta_existente_mais_proxima(alvo)
    try:
        itens = sorted(pasta.iterdir(), key=lambda p: (p.is_file(), p.name))
    except OSError:  # permissao negada, disco removido...
        return ""
    if not itens:
        return f"'{_rotulo(pasta)}' esta vazia."

    nomes = [f"{i.name}/" if i.is_dir() else i.name for i in itens[:MAX_ITENS_NA_DICA]]
    resto = len(itens) - len(nomes)
    if resto > 0:
        nomes.append(f"... (+{resto})")
    return f"Em '{_rotulo(pasta)}' existem: {', '.join(nomes)}"


def _confirmar(titulo: str, corpo: Any = None) -> bool:
    """Human-in-the-loop: pede aprovacao (s/N) antes de uma acao destrutiva.

    `corpo` e qualquer renderavel do rich (texto, Syntax, Group) que da
    contexto para a decisao -- e o que o dev le antes de digitar 's'.

    - Se auto-aprovacao (--yes) estiver ligada, aprova automaticamente.
    - Se a entrada nao for interativa (nao-TTY), NEGA por seguranca em vez
      de travar esperando input que nunca vem.
    """
    if is_auto_approve():
        return True
    if not sys.stdin or not sys.stdin.isatty():
        console.print(
            f"\n[yellow]NEGADO automaticamente[/yellow] [dim](sem terminal "
            f"interativo)[/dim] {escape(titulo)}"
        )
        return False

    console.print()
    console.print(
        Panel(
            corpo if corpo is not None else "",
            title=f"[bold yellow]aprovacao necessaria[/bold yellow]  {escape(titulo)}",
            title_align="left",
            border_style="yellow",
            padding=(1, 2),
        )
    )
    try:
        resposta = console.input("[bold]Aprovar?[/bold] [dim][s/N][/dim] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return False
    aprovado = resposta in ("s", "sim", "y", "yes")
    console.print(
        "[green]  aprovado[/green]" if aprovado else "[red]  recusado[/red]"
    )
    return aprovado


@tool
def list_directory(path: str = ".") -> str:
    """Lista arquivos e pastas dentro do projeto (relativo a raiz do projeto).

    Use para explorar a estrutura antes de decidir mudancas. Comece por "."
    para ver a raiz: o projeto Maven nem sempre esta la (nos repositorios desta
    area ele costuma ficar em `app/`, com o codigo em `app/src/main/java`).
    """
    try:
        target = resolve_inside_project(path)
    except (PermissionError, RuntimeError) as exc:
        return f"ERRO: {exc}"
    if not target.exists():
        return f"ERRO: caminho nao existe: {path}\n{_onde_procurar(target)}".rstrip()
    if not target.is_dir():
        return f"ERRO: nao e um diretorio: {path}"

    linhas: list[str] = []
    for item in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name)):
        # Sempre com barra normal: no Windows o `relative_to` devolveria
        # "app\src\main", e e esse texto que o modelo copia de volta como
        # argumento da proxima chamada. Um so formato evita que ele misture os
        # dois no mesmo caminho.
        marcador = "/" if item.is_dir() else ""
        linhas.append(f"{_rotulo(item)}{marcador}")
    return "\n".join(linhas) if linhas else "(vazio)"


@tool
def read_file(path: str) -> str:
    """Le o conteudo de um arquivo do projeto (relativo a raiz do projeto).

    Use para inspecionar pom.xml, application.properties, classes, etc.
    """
    try:
        target = resolve_inside_project(path)
    except (PermissionError, RuntimeError) as exc:
        return f"ERRO: {exc}"
    if target.is_dir():
        return f"ERRO: isto e um diretorio, nao um arquivo: {path}"
    if not target.is_file():
        return (
            f"ERRO: arquivo nao encontrado: {path}\n{_onde_procurar(target)}"
        ).rstrip()
    try:
        conteudo = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"ERRO: arquivo binario ou encoding nao-UTF8: {path}"
    if len(conteudo) > MAX_READ_CHARS:
        return conteudo[:MAX_READ_CHARS] + "\n\n... [TRUNCADO]"
    return conteudo


@tool
def write_file(path: str, content: str) -> str:
    """Cria ou sobrescreve um arquivo do projeto com o conteudo fornecido.

    Cria as pastas intermediarias automaticamente. Use para gerar/ajustar
    pom.xml, criar pacotes, arquivos de config, etc. Sempre leia o arquivo
    antes de sobrescrever, quando ele ja existir.
    """
    try:
        target = resolve_inside_project(path)
    except (PermissionError, RuntimeError) as exc:
        return f"ERRO: {exc}"

    if not _confirmar(f"escrever em {path}", _previa_da_escrita(path, content, target)):
        return f"CANCELADO: usuario nao aprovou a escrita em {path}"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"OK: {len(content)} caracteres escritos em {path}"


def _previa_da_escrita(path: str, content: str, target) -> Group:
    """Monta o que o dev ve antes de aprovar uma escrita.

    Uma linha dizendo o que vai acontecer e o inicio do conteudo com syntax
    highlighting -- ler XML ou Java colorido e bem mais rapido do que ler um
    bloco cru de texto.
    """
    if target.is_file():
        situacao = Text.assemble(
            ("SOBRESCREVER", "bold red"),
            (f"  arquivo existe, {target.stat().st_size} bytes atuais", "dim"),
        )
    else:
        situacao = Text.assemble(("CRIAR", "bold green"), ("  arquivo novo", "dim"))
    situacao.append(f"  ->  {len(content)} caracteres", style="dim")

    linhas = content.splitlines()
    trecho = "\n".join(linhas[:LINHAS_DE_PREVIA])
    try:
        # guess_lexer usa a extensao do arquivo (e o conteudo como desempate).
        preview = Syntax(
            trecho,
            Syntax.guess_lexer(path, code=trecho),
            line_numbers=True,
            theme="ansi_dark",  # usa a paleta do terminal, clara ou escura
            word_wrap=True,
        )
    except Exception:
        preview = Text(trecho)  # linguagem exotica: mostra cru, mas mostra

    partes: list[Any] = [situacao, "", preview]
    if len(linhas) > LINHAS_DE_PREVIA:
        partes.append(
            Text(f"... (+{len(linhas) - LINHAS_DE_PREVIA} linhas)", style="dim italic")
        )
    return Group(*partes)


@tool
def create_directory(path: str) -> str:
    """Cria uma pasta (e intermediarias) dentro do projeto.

    Use para organizar a estrutura de pacotes (ex.: controller, service, repository).
    """
    try:
        target = resolve_inside_project(path)
    except (PermissionError, RuntimeError) as exc:
        return f"ERRO: {exc}"
    target.mkdir(parents=True, exist_ok=True)
    return f"OK: pasta criada: {path}"


def _pastas_com_pom() -> list[Path]:
    """Onde ha um pom.xml: a raiz, ou as subpastas de primeiro nivel.

    Nos repositorios da area o pom quase nunca esta na raiz -- o projeto Maven
    fica em `app/`, ao lado de `infra/`, `docs/` e afins. Rodar o mvn na raiz
    ali morre com "there is no POM in this directory", que nao diz ao modelo o
    que fazer em seguida.

    Um nivel de profundidade e de proposito: e onde o pom esta nesse layout, e
    varrer o repositorio inteiro traria os poms de exemplo e de teste junto.
    """
    root = get_project_root()
    if (root / "pom.xml").is_file():
        return [root]
    return sorted(
        pasta
        for pasta in root.iterdir()
        if pasta.is_dir()
        and not pasta.name.startswith(".")
        and (pasta / "pom.xml").is_file()
    )


@tool
def run_maven(goals: str = "validate", modulo: str = "") -> str:
    """Executa um comando Maven no projeto e retorna a saida.

    `goals` sao os argumentos do mvn (ex.: "validate", "compile",
    "dependency:tree"). Use para VERIFICAR que as mudancas nao quebraram
    o build. Prefira comandos rapidos como "validate" ou "compile".

    `modulo` e a pasta do pom.xml, relativa a raiz (ex.: "app"). Deixe vazio
    para o agente localizar sozinho -- so preencha se houver mais de um modulo
    e voce souber qual quer.
    """
    if modulo:
        try:
            pasta = resolve_inside_project(modulo)
        except (PermissionError, RuntimeError) as exc:
            return f"ERRO: {exc}"
        if not (pasta / "pom.xml").is_file():
            return f"ERRO: nao ha pom.xml em: {modulo}\n{_onde_procurar(pasta)}".rstrip()
    else:
        candidatas = _pastas_com_pom()
        if not candidatas:
            return (
                "ERRO: nenhum pom.xml encontrado na raiz nem nas pastas de "
                f"primeiro nivel.\n{_onde_procurar(get_project_root())}"
            )
        if len(candidatas) > 1:
            nomes = ", ".join(_rotulo(p) for p in candidatas)
            return (
                f"ERRO: ha mais de um modulo Maven aqui ({nomes}). "
                "Repita a chamada passando `modulo` com o que voce quer."
            )
        pasta = candidatas[0]

    # No Windows o executavel costuma ser mvn.cmd; deixamos o shell resolver.
    comando = f"mvn -B {goals}"

    detalhe = Text.assemble(
        ("$ ", "dim"), (comando, "bold"), ("\n", ""), (f"  em {pasta}", "dim")
    )
    if not _confirmar("executar Maven", detalhe):
        return f"CANCELADO: usuario nao aprovou 'mvn {goals}'"

    try:
        resultado = subprocess.run(
            comando,
            cwd=pasta,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return "ERRO: comando Maven excedeu 300s (timeout)."
    except FileNotFoundError:
        return "ERRO: Maven (mvn) nao encontrado no PATH."

    saida = (resultado.stdout or "") + (resultado.stderr or "")
    if len(saida) > MAX_READ_CHARS:
        saida = saida[-MAX_READ_CHARS:]  # o fim do log costuma ter o erro
    status = "SUCESSO" if resultado.returncode == 0 else f"FALHA (exit {resultado.returncode})"
    # Onde rodou entra na resposta: em repositorio com o pom fora da raiz, o
    # modelo precisa saber qual modulo foi construido para ler o log direito.
    return f"[{status}] mvn {goals} em '{_rotulo(pasta)}'\n{saida}"


@tool
def buscar_conhecimento(consulta: str, limite: int = 0) -> str:
    """Busca na base de conhecimento da area (arquitetura de referencia).

    Use para duvidas sobre PADROES e DECISOES da area: arquitetura de
    referencia, convencoes de projeto, formato dos eventos de auditoria,
    nomenclatura de filas. NAO use para duvidas sobre o codigo deste
    repositorio -- para isso use `list_directory` e `read_file`.

    Escreva a consulta com os termos do dominio, como voce perguntaria a um
    colega da area ("como o worker publica evento de auditoria"). Se o
    resultado nao responder, busque de novo com outras palavras antes de
    desistir.

    `limite` e quantos trechos trazer; 0 usa o padrao configurado.
    """
    try:
        trechos = consultar(consulta, limite=limite)
    except KBIndisponivel as exc:
        # Vira texto (e nao excecao) de proposito: o modelo le o erro, avisa o
        # desenvolvedor e segue com o que sabe, em vez de derrubar o turno.
        return f"ERRO: {exc}"

    if not trechos:
        return (
            "Nenhum trecho encontrado na base para essa consulta. "
            "Tente outros termos ou assuma que a base nao cobre o assunto."
        )

    blocos: list[str] = []
    for indice, trecho in enumerate(trechos, start=1):
        texto = trecho.texto
        if len(texto) > MAX_TRECHO_CHARS:
            texto = texto[:MAX_TRECHO_CHARS] + "\n... [TRUNCADO]"
        cabecalho = f"[{indice}] {trecho.origem}"
        if trecho.score is not None:
            cabecalho += f"  (score {trecho.score:.3f})"
        blocos.append(f"{cabecalho}\n{texto}")
    return "\n\n---\n\n".join(blocos)


# Lista exportada para o grafo montar o ToolNode.
ALL_TOOLS = [
    list_directory,
    read_file,
    write_file,
    create_directory,
    run_maven,
    buscar_conhecimento,
]
