"""Ferramentas que o agente pode chamar.

Cada funcao decorada com @tool vira uma "ferramenta" que o Claude pode
invocar. A descricao (docstring) e o schema (type hints) sao lidos pelo
modelo para decidir QUANDO e COMO chamar cada uma.

Design: ferramentas dedicadas (em vez de um unico `bash`) dao ao harness
um ponto de controle tipado por acao -- ex.: podemos auditar/limitar a
escrita e o Maven separadamente da leitura.
"""

from __future__ import annotations

import subprocess
import sys

from langchain_core.tools import tool

from .config import get_project_root, is_auto_approve, resolve_inside_project

# Limite para nao estourar o contexto do modelo com arquivos gigantes.
MAX_READ_CHARS = 60_000


def _confirmar(titulo: str, detalhe: str = "") -> bool:
    """Human-in-the-loop: pede aprovacao (s/N) antes de uma acao destrutiva.

    - Se auto-aprovacao (--yes) estiver ligada, aprova automaticamente.
    - Se a entrada nao for interativa (nao-TTY), NEGA por seguranca em vez
      de travar esperando input que nunca vem.
    """
    if is_auto_approve():
        return True
    if not sys.stdin or not sys.stdin.isatty():
        print(f"\n[NEGADO automaticamente — sem terminal interativo] {titulo}")
        return False

    print("\n" + "-" * 60)
    print(f"APROVACAO NECESSARIA: {titulo}")
    if detalhe:
        print(detalhe)
    print("-" * 60)
    try:
        resposta = input("Aprovar? [s/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return resposta in ("s", "sim", "y", "yes")


@tool
def list_directory(path: str = ".") -> str:
    """Lista arquivos e pastas dentro do projeto (relativo a raiz do projeto).

    Use para explorar a estrutura antes de decidir mudancas.
    `path` e relativo a raiz do projeto (ex.: "." ou "src/main/java").
    """
    try:
        target = resolve_inside_project(path)
    except (PermissionError, RuntimeError) as exc:
        return f"ERRO: {exc}"
    if not target.exists():
        return f"ERRO: caminho nao existe: {path}"
    if not target.is_dir():
        return f"ERRO: nao e um diretorio: {path}"

    root = get_project_root()
    linhas: list[str] = []
    for item in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name)):
        rel = item.relative_to(root)
        marcador = "/" if item.is_dir() else ""
        linhas.append(f"{rel}{marcador}")
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
    if not target.is_file():
        return f"ERRO: arquivo nao encontrado: {path}"
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

    # Monta um preview para o usuario decidir com contexto.
    if target.is_file():
        tamanho_atual = target.stat().st_size
        situacao = f"SOBRESCREVER (arquivo existe, {tamanho_atual} bytes atuais)"
    else:
        situacao = "CRIAR (arquivo novo)"
    linhas = content.splitlines()
    preview = "\n".join(linhas[:15])
    if len(linhas) > 15:
        preview += f"\n... (+{len(linhas) - 15} linhas)"
    detalhe = (
        f"Arquivo: {path}\n"
        f"Acao: {situacao} -> {len(content)} caracteres\n"
        f"--- previa do conteudo ---\n{preview}"
    )
    if not _confirmar(f"escrever em {path}", detalhe):
        return f"CANCELADO: usuario nao aprovou a escrita em {path}"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"OK: {len(content)} caracteres escritos em {path}"


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


@tool
def run_maven(args: str = "validate") -> str:
    """Executa um comando Maven na raiz do projeto e retorna a saida.

    `args` sao os argumentos do mvn (ex.: "validate", "compile",
    "dependency:tree"). Use para VERIFICAR que as mudancas nao quebraram
    o build. Prefira comandos rapidos como "validate" ou "compile".
    """
    root = get_project_root()
    # No Windows o executavel costuma ser mvn.cmd; deixamos o shell resolver.
    comando = f"mvn -B {args}"

    if not _confirmar(f"executar Maven: {comando}", f"Pasta: {root}"):
        return f"CANCELADO: usuario nao aprovou 'mvn {args}'"

    try:
        resultado = subprocess.run(
            comando,
            cwd=root,
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
    return f"[{status}]\n{saida}"


# Lista exportada para o grafo montar o ToolNode.
ALL_TOOLS = [
    list_directory,
    read_file,
    write_file,
    create_directory,
    run_maven,
]
