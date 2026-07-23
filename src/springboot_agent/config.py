"""Configuracao central do agente.

O `project_root` e um estado global do processo: definimos ele uma vez
(no `main.py`, a partir do argumento de linha de comando) e as ferramentas
em `tools.py` resolvem todos os caminhos contra ele. Isso garante que o
agente so consiga ler/escrever DENTRO do projeto Spring Boot alvo.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Modelo Claude usado pelo agente. claude-opus-4-8 e o mais capaz para
# tarefas de codigo/edicao de arquivos.
MODEL_NAME: str = os.getenv("AGENT_MODEL", "claude-opus-4-8")

# Raiz do projeto Spring Boot que o agente vai configurar.
# Definido em runtime via set_project_root().
_project_root: Path | None = None

# Modo de auto-aprovacao: quando True, as ferramentas destrutivas
# (write_file, run_maven) NAO pedem confirmacao. Ligado pela flag --yes.
_auto_approve: bool = False


def set_auto_approve(value: bool) -> None:
    """Liga/desliga a auto-aprovacao (pular confirmacoes)."""
    global _auto_approve
    _auto_approve = value


def is_auto_approve() -> bool:
    return _auto_approve


def set_project_root(path: str | os.PathLike[str]) -> Path:
    """Define (uma vez) a pasta do projeto Spring Boot alvo."""
    global _project_root
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        raise NotADirectoryError(f"Nao e um diretorio valido: {resolved}")
    _project_root = resolved
    return resolved


def get_project_root() -> Path:
    if _project_root is None:
        raise RuntimeError(
            "project_root nao definido. Chame set_project_root() antes de usar as tools."
        )
    return _project_root


def resolve_inside_project(relative_or_absolute: str) -> Path:
    """Resolve um caminho e garante que ele fica dentro do projeto.

    Barreira de seguranca: impede que o agente escape da pasta alvo
    (via '..', symlinks ou caminhos absolutos externos).
    """
    root = get_project_root()
    candidate = (root / relative_or_absolute).resolve()
    if root != candidate and root not in candidate.parents:
        raise PermissionError(
            f"Caminho fora do projeto e bloqueado: {relative_or_absolute}"
        )
    return candidate
