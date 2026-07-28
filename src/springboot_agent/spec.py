"""A spec do projeto: o artefato que o /initialize produz.

O /initialize nao toca em nenhum arquivo do projeto. Ele apenas coleta as
respostas e grava este JSON:

    <raiz-do-projeto>/.springboot-agent/spec.json

Por que separar "coletar" de "aplicar"
--------------------------------------
Os proximos comandos (/generate, /infra, ...) leem a spec e aplicam as
mudancas. Isso deixa cada etapa auditavel e repetivel:

- a spec entra no git, entao da para revisar em pull request o que foi
  decidido, separado do codigo que foi gerado;
- rodar o gerador de novo com a mesma spec produz o mesmo resultado;
- se um dia um comando usar LLM para gerar codigo, a spec continua sendo a
  fronteira deterministica -- o que foi DECIDIDO nunca depende do modelo.

`SPEC_VERSION` existe para migracao: quando o formato mudar, os comandos
conseguem detectar uma spec antiga e avisar em vez de interpretar errado.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Versao do FORMATO do arquivo (nao do agente).
SPEC_VERSION = 1

# Pasta e arquivo, relativos a raiz do projeto alvo.
SPEC_DIR = ".springboot-agent"
SPEC_FILENAME = "spec.json"


class SpecError(RuntimeError):
    """Falha ao ler ou interpretar uma spec existente."""


@dataclass
class SqsConfig:
    """Configuracao do consumo SQS."""

    queue_name: str
    messages_per_second: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "queue_name": self.queue_name,
            "messages_per_second": self.messages_per_second,
        }

    @staticmethod
    def from_dict(dados: dict[str, Any]) -> SqsConfig:
        return SqsConfig(
            queue_name=str(dados["queue_name"]),
            messages_per_second=int(dados["messages_per_second"]),
        )


@dataclass
class ProjectSpec:
    """O que foi decidido sobre o projeto."""

    project_type: str                     # "worker"
    trigger: str                          # "sqs"
    dependencies: list[str] = field(default_factory=list)
    sqs: SqsConfig | None = None
    spec_version: int = SPEC_VERSION
    generated_at: str = ""                # ISO-8601 UTC
    generated_by: str = ""

    # -- serializacao ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_version": self.spec_version,
            "generated_at": self.generated_at,
            "generated_by": self.generated_by,
            "project": {
                "type": self.project_type,
                "trigger": self.trigger,
                "sqs": self.sqs.to_dict() if self.sqs else None,
                "dependencies": list(self.dependencies),
            },
        }

    @staticmethod
    def from_dict(dados: dict[str, Any]) -> ProjectSpec:
        try:
            projeto = dados["project"]
            sqs = projeto.get("sqs")
            return ProjectSpec(
                project_type=str(projeto["type"]),
                trigger=str(projeto["trigger"]),
                dependencies=list(projeto.get("dependencies") or []),
                sqs=SqsConfig.from_dict(sqs) if sqs else None,
                spec_version=int(dados.get("spec_version", 0)),
                generated_at=str(dados.get("generated_at", "")),
                generated_by=str(dados.get("generated_by", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SpecError(f"spec.json com formato inesperado: {exc}") from exc


# ---------------------------------------------------------------------------
# Leitura e escrita em disco
# ---------------------------------------------------------------------------

def spec_path(project_root: Path) -> Path:
    """Caminho do spec.json dentro do projeto alvo."""
    return project_root / SPEC_DIR / SPEC_FILENAME


def spec_exists(project_root: Path) -> bool:
    return spec_path(project_root).is_file()


def save_spec(project_root: Path, spec: ProjectSpec, *, agent_version: str) -> Path:
    """Grava a spec (sobrescrevendo se ja existir) e devolve o caminho."""
    spec.generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    spec.generated_by = agent_version

    destino = spec_path(project_root)
    destino.parent.mkdir(parents=True, exist_ok=True)
    # ensure_ascii=False para acentos legiveis; sort_keys=False para manter a
    # ordem que escrevemos em to_dict(), que e a ordem que faz sentido ler.
    conteudo = json.dumps(spec.to_dict(), indent=2, ensure_ascii=False) + "\n"
    destino.write_text(conteudo, encoding="utf-8")
    return destino


def load_spec(project_root: Path) -> ProjectSpec | None:
    """Le a spec do projeto. Devolve None se ainda nao existir.

    Levanta SpecError se o arquivo existir mas estiver corrompido ou for de
    uma versao de formato que este agente nao entende.
    """
    origem = spec_path(project_root)
    if not origem.is_file():
        return None
    try:
        dados = json.loads(origem.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SpecError(f"nao foi possivel ler {origem}: {exc}") from exc
    if not isinstance(dados, dict):
        raise SpecError(f"{origem} nao contem um objeto JSON.")

    spec = ProjectSpec.from_dict(dados)
    if spec.spec_version > SPEC_VERSION:
        raise SpecError(
            f"{origem} foi gerado por uma versao mais nova do agente "
            f"(formato {spec.spec_version}, este agente entende ate {SPEC_VERSION}). "
            "Atualize o springboot-agent."
        )
    return spec
