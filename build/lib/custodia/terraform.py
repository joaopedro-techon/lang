"""Escreve o terraform do worker no projeto alvo.

Duas fontes formam o resultado:

- os arquivos de `templates/worker/terraform/`, que viajam dentro da wheel e
  sao copiados (alguns com marcadores `{{X}}` trocados pelas respostas);
- o `terraform.tfvars` de cada ambiente, montado aqui em codigo -- porque ele
  tem listas e blocos que dependem do que veio da AWS, e um template de texto
  com furos no meio de uma lista fica ilegivel.

Os marcadores usam `{{...}}` de proposito: o HCL usa `${...}` para interpolar,
entao nao ha risco de trocar por engano uma interpolacao de verdade do
terraform (`${local.sigla}` continua intacto).

REGRA DURA: nada e escrito fora de `<projeto>/**/infra/`. `_dentro_da_infra()`
verifica caminho por caminho antes de qualquer escrita.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from .dimensionamento import (
    COOLDOWN_DESCIDA_S,
    COOLDOWN_SUBIDA_S,
    PERIODOS_DESCIDA,
    PERIODOS_SUBIDA,
    Dimensionamento,
)

# Arquivos copiados sem nenhuma substituicao.
_VERBATIM = (
    "provider.tf",
    "iamsr.tf",
    "main.tf",
    "outputs.tf",
    "variables.tf",
    "iamsr/policy/policy-execution-autoscale.json",
    "iamsr/policy/policy-execution-ecs.json",
    "iamsr/trust/trust-execution-autoscale.json",
    "iamsr/trust/trust-execution-ecs.json",
)

# Arquivos com marcadores.
_COM_MARCADORES = ("data.tf", "locals.tf")

# Valores que o template ja trazia fixos e que nao perguntamos.
TASK_CPU = 1024
TASK_MEMORY = 2048
EPHEMERAL_STORAGE_GIB = 50


class InfraNaoEncontrada(RuntimeError):
    """Nao ha uma pasta infra/terraform identificavel no projeto."""


@dataclass(frozen=True)
class Ambiente:
    """Tudo o que foi decidido para UM ambiente."""

    nome: str                    # dev | hom | prod
    ecs_cluster_name: str
    vpc_id: str
    subnets: list[str]
    cidr_blocks: list[str]
    container_port: int
    queue_names: list[str]
    sts_internal_url: str
    sts_external_url: str
    dimensionamento: Dimensionamento


# ---------------------------------------------------------------------------
# Onde fica a infra
# ---------------------------------------------------------------------------

def localizar_infra(project_root: Path) -> Path:
    """Acha a pasta `infra/terraform` do projeto.

    Nos repositorios da area ela fica em `<repo>/app/infra/terraform`, mas nao
    dependemos disso: procuramos ate dois niveis abaixo da raiz. Se houver mais
    de uma, falamos qual e a ambiguidade em vez de escolher sozinhos.
    """
    candidatos = [project_root / "infra" / "terraform"]
    candidatos += sorted(project_root.glob("*/infra/terraform"))

    encontradas = [c for c in candidatos if c.is_dir()]
    if not encontradas:
        raise InfraNaoEncontrada(
            f"nao encontrei uma pasta 'infra/terraform' em {project_root}.\n"
            "O /infra parte de um projeto que ja tem a estrutura de infra."
        )
    if len(encontradas) > 1:
        lista = "\n  ".join(str(c) for c in encontradas)
        raise InfraNaoEncontrada(
            f"encontrei mais de uma pasta de infra:\n  {lista}\n"
            "Rode o /infra apontando direto para o projeto certo."
        )
    return encontradas[0]


def _dentro_da_infra(caminho: Path, raiz_infra: Path) -> Path:
    """Barreira: garante que uma escrita cai dentro da infra.

    O /infra so tem permissao de mexer em infra/. Esta checagem e o que impede
    um marcador com '..' ou um nome de arquivo inesperado de escapar.
    """
    alvo = caminho.resolve()
    raiz = raiz_infra.resolve()
    if raiz != alvo and raiz not in alvo.parents:
        raise PermissionError(f"escrita fora da pasta de infra bloqueada: {caminho}")
    return alvo


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def _base_templates():
    return resources.files("custodia") / "templates" / "worker" / "terraform"


def _ler_template(nome: str) -> str:
    caminho = _base_templates()
    for parte in nome.split("/"):
        caminho = caminho / parte
    return caminho.read_text(encoding="utf-8")


def _aplicar(texto: str, valores: dict[str, str]) -> str:
    """Troca cada `{{CHAVE}}` pelo valor. Sobra de marcador e erro, nao silencio."""
    for chave, valor in valores.items():
        texto = texto.replace("{{" + chave + "}}", str(valor))
    if "{{" in texto:
        restante = texto[texto.index("{{") : texto.index("{{") + 40]
        raise KeyError(f"marcador nao substituido no template: {restante!r}")
    return texto


# ---------------------------------------------------------------------------
# Geracao do terraform.tfvars
# ---------------------------------------------------------------------------

def _lista_hcl(valores: list[str], indent: str = "  ", fecho: str = "") -> str:
    """Lista HCL multilinha. `fecho` alinha o ']' quando a lista esta aninhada."""
    if not valores:
        return "[]"
    linhas = ",\n".join(f'{indent}"{v}"' for v in valores)
    return "[\n" + linhas + f"\n{fecho}]"


def render_tfvars(ambiente: Ambiente, nome_do_log: str) -> str:
    """Monta o terraform.tfvars de um ambiente."""
    d = ambiente.dimensionamento
    return f"""\
############## definicoes basicas do service
environment = "{ambiente.nome}"

ecs_cluster_name = "{ambiente.ecs_cluster_name}"

service_desired_count = {d.min_capacity}

autoscaling = {{
  min_capacity = {d.min_capacity}
  max_capacity = {d.max_capacity}
  scale_up = {{
    threshold          = {d.threshold_subida} # backlog equivalente a {COOLDOWN_SUBIDA_S}s de trabalho da frota
    cooldown           = {COOLDOWN_SUBIDA_S}
    evaluation_periods = {PERIODOS_SUBIDA}
    steps = [
      {{ lower_bound = 0, upper_bound = null, scaling_adjustment = 1 }}
    ]
  }}
  scale_down = {{
    threshold          = {d.threshold_descida}
    cooldown           = {COOLDOWN_DESCIDA_S}
    evaluation_periods = {PERIODOS_DESCIDA}
    steps = [
      {{ lower_bound = null, upper_bound = 0, scaling_adjustment = -1 }}
    ]
  }}
  queue_names = {_lista_hcl(ambiente.queue_names, indent="    ", fecho="  ")}
}}

service_launch_config = {{
  launch_type = "FARGATE"
  capacity_providers = [
    {{
      capacity_provider = "FARGATE"
      base              = 1
      weight            = 1
    }}
  ]
}}

############## configuracoes minimas de rede
service_vpc_id = "{ambiente.vpc_id}"

service_cidr_blocks = {_lista_hcl(ambiente.cidr_blocks)}

service_subnets = {_lista_hcl(ambiente.subnets)}

task_container_port = [
  {{
    containerPort = {ambiente.container_port}
  }}
]

############## definicoes basicas do container
task_cpu = {TASK_CPU}

task_memory = {TASK_MEMORY}

task_ulimits_vars = [
  {{
    name      = "nofile"
    softLimit = 2048
    hardLimit = 8192
  }}
]

task_ephemeral_storage_size_in_gib = {EPHEMERAL_STORAGE_GIB}

task_log_driver = {{
  log-driver = "awsfirelens"
  options = {{
    Name = "{nome_do_log}"
  }}
}}

############## STS
sts_internal_url = "{ambiente.sts_internal_url}"

sts_external_url = "{ambiente.sts_external_url}"
"""


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------

def escrever_infra(
    project_root: Path, identidade: dict[str, Any], ambientes: list[Ambiente]
) -> list[Path]:
    """Escreve o terraform do worker e devolve os caminhos tocados.

    `identidade` traz o que vale para o projeto inteiro (sigla, produto,
    emails, nome do secret); `ambientes` traz o que muda por ambiente.
    Ambientes nao selecionados nao sao tocados -- o tfvars deles fica como
    estava.
    """
    raiz_infra = localizar_infra(project_root)
    escritos: list[Path] = []

    marcadores = {
        "SECRET_NAME": identidade["secret_name"],
        "SIGLA": identidade["sigla"],
        "SIGLA_APP": identidade["sigla_app"],
        "PRODUTO": identidade["produto"],
        "CONTEXT": identidade["context"],
        "OWNER_EMAIL": identidade["owner_email"],
        "TECH_EMAIL": identidade["tech_email"],
        "SQUAD": identidade["squad"],
        "FEATURE_NAME": identidade["feature_name"],
        "MICROSERVICE_NAME": identidade["microservice_name"],
        "FINOPS_SQUAD": identidade["finops_squad"],
        "FINOPS_PRODUTO": identidade["finops_produto"],
        "FINOPS_PROJETO": identidade["finops_projeto"],
        "FINOPS_OFERTA": identidade["finops_oferta"],
        "FINOPS_SERVICO": identidade["finops_servico"],
    }

    for nome in _VERBATIM:
        escritos.append(_gravar(raiz_infra, nome, _ler_template(nome)))

    for nome in _COM_MARCADORES:
        escritos.append(_gravar(raiz_infra, nome, _aplicar(_ler_template(nome), marcadores)))

    nome_do_log = (
        f"{identidade['sigla']}-{identidade['feature_name']}-"
        f"{identidade['microservice_name']}"
    )
    for ambiente in ambientes:
        destino = f"inventories/{ambiente.nome}/terraform.tfvars"
        escritos.append(_gravar(raiz_infra, destino, render_tfvars(ambiente, nome_do_log)))

    return escritos


def _gravar(raiz_infra: Path, relativo: str, conteudo: str) -> Path:
    alvo = _dentro_da_infra(raiz_infra / relativo, raiz_infra)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(conteudo, encoding="utf-8")
    return alvo
