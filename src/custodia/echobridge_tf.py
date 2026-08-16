"""Escreve a infra do EchoBridge no projeto alvo.

O projeto que o desenvolvedor recebe vem no formato de worker: `infra/terraform`
com `iamsr.tf`, as policies e um `main.tf` que sobe um servico proprio. O
EchoBridge nao e nada disso -- ele consome UM modulo pronto
(`itau-hn8-modules-ecs-echobridge`), que ja traz IAM, task definition e
autoscaling. Configurar o projeto e, entao, tres movimentos:

1. TROCAR o terraform do worker pelo do connector (main/variables/outputs/
   provider/data), sempre igual, porque quem decide o que existe e o modulo;
2. ESCREVER o que muda de projeto para projeto -- `locals.tf` (identidade,
   filtros, transformacao), o `terraform.tfvars` de cada ambiente e o
   `mappers/sink_transformation.json`;
3. TIRAR o que sobrou do worker (`iamsr.tf` e `iamsr/`), que o modulo nao usa e
   que, deixado para tras, faz o `terraform plan` tentar criar roles orfas.

Os marcadores usam `{{...}}` de proposito, como no `terraform.py`: o HCL usa
`${...}` para interpolar, entao nao ha risco de trocar por engano uma
interpolacao de verdade (`${path.module}` continua intacto).

REGRA DURA: alem de `infra/`, este modulo escreve UM arquivo na raiz do
repositorio -- o `.iupipes.yml`, que e a esteira e nao poderia morar em outro
lugar. `_dentro_do_repositorio()` verifica caminho por caminho antes de
qualquer escrita, e nada sobe acima da raiz do repositorio.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from .questions import IMAGEM_ECHOBRIDGE
from .terraform import localizar_infra

# Copiados sem nenhuma substituicao: o que existe aqui e decidido pelo modulo,
# nao pelo projeto.
_VERBATIM = ("provider.tf", "outputs.tf")

# Copiados com marcadores.
_COM_MARCADORES = ("main.tf", "variables.tf", "data.tf")

# Sobras do template de worker que o EchoBridge nao usa. O modulo cria as roles
# sozinho; estes arquivos deixados para tras viram recurso orfao no plan.
SOBRAS_DO_WORKER = ("iamsr.tf", "iamsr")

# Fixos porque a area padronizou, nao porque o modulo obrigue.
OBSERVABILIDADE = "DATADOG"
TRACE_HABILITADO = True


@dataclass(frozen=True)
class Topico:
    """Um topico Kafka consumido pelo connector.

    Nome, broker, schema, filtro e mapeamento sao propriedades do TOPICO e nao
    mudam de ambiente para ambiente. O numero de particoes NAO esta aqui de
    proposito: ele muda -- o mesmo topico costuma ter menos particoes em dev do
    que em producao -- entao mora no ambiente, em `AmbienteEcho.particoes`.
    """

    nome: str
    broker: int          # indice dentro do `bootstrap` do ambiente
    schema: str          # "governado" | "sem"
    clazz: str = ""      # o sourceType do evento (usado no filtro e no mapper)
    # {} ou algum de {"header": {...}, "clazz": {...}, "body": {...}}
    filtro: dict[str, Any] = field(default_factory=dict)
    # [{"source"|"constant": ..., "target": ...}, ...]
    mapeamentos: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class AmbienteEcho:
    """Tudo o que foi decidido para UM ambiente."""

    nome: str            # dev | hom | prod
    conta: str
    regiao: str
    ecs_cluster_name: str
    profile: str
    vpc_id: str
    subnets: list[str]
    cidr_blocks: list[str]
    security_group: str
    kafka_client_id: str
    kafka_group_id: str
    bootstrap: list[str]  # um por broker, na ordem do indice em Topico.broker
    particoes: dict[str, int]  # nome do topico -> particoes NESTE ambiente
    messaging_arn: str
    retencao_dias: int
    log_level: str


# ---------------------------------------------------------------------------
# Barreira de escrita
# ---------------------------------------------------------------------------

def raiz_do_repositorio(raiz_infra: Path) -> Path:
    """Onde mora o `.iupipes.yml`: o diretorio que CONTEM o `infra/`.

    Nao e a raiz onde a CLI rodou: nos repositorios da area a infra as vezes
    fica em `<repo>/app/infra/terraform`, e a esteira daquele modulo mora junto
    do `infra/`, nao no topo do monorepo.
    """
    return raiz_infra.parent.parent


def _dentro_do_repositorio(caminho: Path, raiz: Path) -> Path:
    """Barreira: garante que uma escrita cai dentro do repositorio."""
    alvo = caminho.resolve()
    base = raiz.resolve()
    if base != alvo and base not in alvo.parents:
        raise PermissionError(f"escrita fora do repositorio bloqueada: {caminho}")
    return alvo


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def _ler_template(nome: str) -> str:
    caminho = resources.files("custodia") / "templates" / "echobridge" / "terraform"
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
# HCL
# ---------------------------------------------------------------------------

def _txt(valor: str) -> str:
    """Uma string HCL, com aspas e barras escapadas."""
    escapado = str(valor).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escapado}"'


def _lista(valores: list[str], recuo: str, inline_ate: int = 0) -> str:
    """Lista HCL de strings, uma por linha. Vazia vira `[]`.

    `inline_ate` deixa a lista numa linha so quando ela cabe. Serve para os
    filtros, onde `values = ["EP9"]` numa linha e mais legivel do que tres
    linhas para um valor -- mas uma lista de nomes de classe Java, que passa
    facil de cem caracteres, continua quebrando.
    """
    if not valores:
        return "[]"
    uma_linha = "[" + ", ".join(_txt(v) for v in valores) + "]"
    if inline_ate and len(uma_linha) + len(recuo) <= inline_ate:
        return uma_linha
    corpo = ",\n".join(f"{recuo}  {_txt(v)}" for v in valores)
    return "[\n" + corpo + f"\n{recuo}]"


def _numeros(valores: list[int]) -> str:
    return "[" + ", ".join(str(v) for v in valores) + "]"


def _bool(valor: bool) -> str:
    return "true" if valor else "false"


# ---------------------------------------------------------------------------
# locals.tf
# ---------------------------------------------------------------------------

def _criterio_hcl(nome: str, criterio: dict[str, Any], recuo: str) -> list[str]:
    """Um bloco `header`/`clazz`/`body` de um filtro."""
    linhas = [f"{recuo}{nome} = {{"]
    if criterio.get("name"):
        linhas.append(f"{recuo}  name      = {_txt(criterio['name'])}")
    linhas.append(
        f"{recuo}  values    = {_lista(criterio['values'], recuo + '  ', inline_ate=60)}"
    )
    linhas.append(f"{recuo}  condition = {_txt(criterio['condition'])}")
    linhas.append(f"{recuo}}}")
    return linhas


def render_filtro(topicos: list[Topico]) -> str:
    """O `sink_kafka_topic_filter`: uma entrada por topico QUE TEM filtro.

    Topico sem filtro simplesmente nao aparece na lista -- e assim que o modulo
    entende "publique tudo deste topico". Incluir uma entrada vazia teria o
    efeito oposto do esperado.
    """
    com_filtro = [t for t in topicos if t.filtro]
    if not com_filtro:
        return "[]"

    blocos: list[str] = []
    for topico in com_filtro:
        linhas = ["    {", f"      topic_name = {_txt(topico.nome)}"]
        for nome in ("header", "clazz", "body"):
            criterio = topico.filtro.get(nome)
            if criterio:
                linhas += _criterio_hcl(nome, criterio, "      ")
        linhas.append("    }")
        blocos.append("\n".join(linhas))

    return "[\n" + ",\n".join(blocos) + "\n  ]"


def render_locals(aplicacao: dict[str, Any], topicos: list[Topico], fifo: bool) -> str:
    """O locals.tf: a identidade do connector e as regras que nao mudam por ambiente."""
    # Sem transformacao o modulo espera `null`, nao um arquivo vazio: ele usa a
    # presenca do valor para decidir se roda o estagio de mapeamento.
    if aplicacao["usa_transformacao"]:
        transformacao = (
            'jsondecode(file("${path.module}/mappers/sink_transformation.json"))'
        )
    else:
        transformacao = "null"

    return f"""\
locals {{
  ############## identidade da aplicacao
  sink_comunidade = {_txt(aplicacao["comunidade"])}

  sink_sigla = {_txt(aplicacao["sigla"])}

  sink_context = {_txt(aplicacao["context"])}

  sink_owner_contact_email = {_txt(aplicacao["owner_email"])}

  sink_tech_team_email = {_txt(aplicacao["tech_email"])}

  sink_finalidade = {_txt(aplicacao["finalidade"])}

  sink_squad = {_txt(aplicacao["squad"])}

  sink_feature_name = {_txt(aplicacao["feature_name"])}

  sink_microservice_name = {_txt(aplicacao["microservice_name"])}

  ############## credenciais do Kafka (kcert), lidas do Secrets Manager
  secret_string = jsondecode(data.aws_secretsmanager_secret_version.kafka_kcert.secret_string)

  ############## destino da publicacao
  sink_messaging_fifo = {_bool(fifo)}

  sink_messaging_service = {{
    type = {_txt(aplicacao["destino"])}
  }}

  ############## observabilidade
  sink_observability_backend       = {_txt(OBSERVABILIDADE)}
  sink_observability_trace_enabled = {_bool(TRACE_HABILITADO)}

  ############## transformacao do payload antes de publicar
  sink_transformation_filter_data = {transformacao}

  ############## quais eventos do Kafka o connector aceita
  # Um evento que atende a PELO MENOS UM filtro da lista nao e descartado.
  # Dentro do mesmo objeto, header/clazz/body sao avaliados com AND.
  # Topico que nao aparece aqui e publicado por inteiro.
  sink_kafka_topic_filter = {render_filtro(topicos)}
}}
"""


# ---------------------------------------------------------------------------
# mappers/sink_transformation.json
# ---------------------------------------------------------------------------

def render_transformacao(topicos: list[Topico]) -> str:
    """O mapper: como o payload de cada evento vira o payload publicado.

    `source` copia um campo; `additionalTransform.constant` injeta um valor
    fixo. Sao as duas formas que o modulo aceita, e o wizard so coleta essas.
    """
    mapeamentos = []
    for topico in topicos:
        if not topico.mapeamentos:
            continue
        regras: list[dict[str, Any]] = []
        for regra in topico.mapeamentos:
            if "constant" in regra:
                regras.append(
                    {
                        "target": regra["target"],
                        "additionalTransform": {"constant": regra["constant"]},
                    }
                )
            else:
                regras.append({"source": regra["source"], "target": regra["target"]})
        mapeamentos.append({"sourceType": topico.clazz, "mapping": regras})

    return json.dumps({"mappings": mapeamentos}, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# inventories/<ambiente>/terraform.tfvars
# ---------------------------------------------------------------------------

def _grupos_de_topicos(
    topicos: list[Topico], ambiente: AmbienteEcho, schema: str
) -> list[dict[str, Any]]:
    """Agrupa os topicos por broker, que e o formato que o modulo espera.

    Cada entrada da lista e um broker com os topicos dele e as particoes de
    cada um -- `topics` e `partitions` sao listas paralelas, na mesma ordem.
    Broker sem topico daquele tipo de schema nao vira entrada.

    As particoes saem de `ambiente.particoes`, nao do topico: e o unico numero
    do connector que muda de ambiente para ambiente.
    """
    grupos = []
    for indice, servidor in enumerate(ambiente.bootstrap):
        do_grupo = [t for t in topicos if t.broker == indice and t.schema == schema]
        if do_grupo:
            grupos.append(
                {
                    "bootstrap_servers": [servidor],
                    "topics": [t.nome for t in do_grupo],
                    "partitions": [ambiente.particoes[t.nome] for t in do_grupo],
                }
            )
    return grupos


def _grupos_hcl(grupos: list[dict[str, Any]]) -> str:
    if not grupos:
        return "[]"
    blocos = []
    for grupo in grupos:
        blocos.append(
            "  {\n"
            f"    bootstrap_servers = {_lista(grupo['bootstrap_servers'], '    ')}\n"
            f"    topics            = {_lista(grupo['topics'], '    ')}\n"
            f"    partitions        = {_numeros(grupo['partitions'])}\n"
            "  }"
        )
    return "[\n" + ",\n".join(blocos) + "\n]"


def render_tfvars(
    aplicacao: dict[str, Any], ambiente: AmbienteEcho, topicos: list[Topico]
) -> str:
    """O terraform.tfvars de um ambiente."""
    governados = _grupos_de_topicos(topicos, ambiente, "governado")
    sem_schema = _grupos_de_topicos(topicos, ambiente, "sem")

    tags = {
        "sigla-app": aplicacao["sigla_app"],
        "contexto": aplicacao["context"],
        "finalidade": aplicacao["finalidade"],
        "iu:finops:alocacao:squad": aplicacao["squad"],
        "iu:finops:alocacao:sigla": aplicacao["sigla"].lower(),
        "iu:finops:alocacao:sigla-app": aplicacao["sigla_app"],
        "iu:finops:alocacao:produto": aplicacao["produto_finops"],
        "iu:finops:alocacao:empresa": aplicacao["empresa"],
        "MicroServiceName": aplicacao["microservice_name"],
        "tech-team-email": aplicacao["tech_email"],
        "owner-team-email": aplicacao["owner_email"],
    }
    # Alinha o "=" de todas as tags: o bloco e longo e uma coluna torta esconde
    # a tag faltando no meio dele.
    largura = max(len(_txt(c)) for c in tags)
    linhas_tags = "\n".join(
        f"  {_txt(c).ljust(largura)} = {_txt(v)}" for c, v in tags.items()
    )

    # `sink_schema_less_topics` so aparece quando ha topico sem schema: uma
    # lista vazia no tfvars sugere que alguem ia preencher e esqueceu.
    bloco_sem_schema = (
        f"\nsink_schema_less_topics = {_grupos_hcl(sem_schema)}\n"
        if sem_schema
        else ""
    )

    return f"""\
############## definicoes basicas do service
sink_environment = {_txt(ambiente.nome)}

profile = {_txt(ambiente.profile)}

sink_ecs_cluster_name = {_txt(ambiente.ecs_cluster_name)}

sink_service_launch_config = {{
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
sink_service_vpc_id = {_txt(ambiente.vpc_id)}

sink_service_cidr_blocks = {_lista(ambiente.cidr_blocks, "")}

sink_service_subnets = {_lista(ambiente.subnets, "")}

sink_security_group_default = {_txt(ambiente.security_group)}

############## Kafka
sink_kafka_client_id = {_txt(ambiente.kafka_client_id)}

sink_kafka_group_id = {_txt(ambiente.kafka_group_id)}

# topics e partitions sao listas paralelas: o topico da posicao N usa a
# particao da posicao N. Estas particoes sao as de {ambiente.nome}.
sink_schema_topics = {_grupos_hcl(governados)}
{bloco_sem_schema}
############## destino
sink_messaging_arn = {_txt(ambiente.messaging_arn)}

############## observabilidade
sink_logging = {{
  retention_in_days = {ambiente.retencao_dias}
  log_level         = {_txt(ambiente.log_level)}
}}

############## tags
sink_additional_tags = {{
{linhas_tags}
}}
"""


# ---------------------------------------------------------------------------
# .iupipes.yml
# ---------------------------------------------------------------------------

def _yaml_txt(valor: str) -> str:
    return "'" + str(valor).replace("'", "''") + "'"


def render_iupipes(aplicacao: dict[str, Any], ambientes: list[AmbienteEcho]) -> str:
    """A esteira. Tudo aqui e derivado -- nao ha pergunta so para o .iupipes.yml.

    Os nomes de ECS seguem a convencao da area (`service-<feature>-<micro>`), e
    conta e regiao vem do `get-caller-identity` que o wizard ja fez no perfil
    daquele ambiente: sao os mesmos numeros que o dev viu na tela de conferencia.
    """
    feature = aplicacao["feature_name"]
    micro = aplicacao["microservice_name"]
    base = f"{feature}-{micro}"

    blocos_deploy = []
    for ambiente in ambientes:
        blocos_deploy.append(
            f"""    {ambiente.nome}:
      account: "{ambiente.conta}"
      region: "{ambiente.regiao}"
      ecs:
        service: {_yaml_txt('service-' + base)}
        cluster: {_yaml_txt(ambiente.ecs_cluster_name)}
        application: {_yaml_txt(base)}
        deployment-group: {_yaml_txt(base)}
        container-name: {_yaml_txt('container-' + base)}"""
        )

    # O taac roda em dev e hom; prod herda o que passou em hom. `failOnError`
    # so em hom de proposito: quebrar o build de dev por achado de esteira
    # travaria o desenvolvimento sem impedir nada em producao.
    blocos_taac = []
    for ambiente in ambientes:
        if ambiente.nome == "prod":
            continue
        blocos_taac.append(
            f"""  {ambiente.nome}:
    failOnError: {_bool(ambiente.nome == "hom")}
    codebuild:
      computeType: "BUILD_GENERAL1_LARGE\""""
        )
    secao_taac = ("taac:\n" + "\n".join(blocos_taac) + "\n\n") if blocos_taac else ""
    secao_deploy = "\n".join(blocos_deploy)
    imagem = f"{IMAGEM_ECHOBRIDGE}:{aplicacao['image_tag']}"

    return f"""\
#Documentacao: https://ideal-bassoon-12961ef9.pages.github.io/jornadas/cloud-publica/aws/ecs/imagem/
project:
  language: deploy-docker-ecs

publish:
  image: {_yaml_txt(imagem)}

build:
  docker-platform: 'linux/arm64'

infra:
  terraform:
    # Obrigatorio
    working-directory: 'infra/terraform'
    version: "1.5.7"
    log-trace: "false"
    aws-statefile-acl: "private"
    aws-s3-data-retention: 0
    aws-s3-data-classification: "Interna"
    aws-tech-team-email: "{aplicacao['tech_email']}"
    aws-owner-contact-email: "{aplicacao['owner_email']}"
    destroy: 'false'

deploy:
  aws:
    noLoadbalancer: "true"
{secao_deploy}

{secao_taac}security:
  extra-command: "ls && rm pom.xml && ls && npm config set strict-ssl false && npm install  --non-interactive --verbose"
  fortify:
    environment-analyse: 'public_cloud'
    nome-aws: {_yaml_txt(micro)}
    produto-aws: {_yaml_txt(feature)}
    sigla-app: {_yaml_txt(aplicacao['sigla_app'])}
    sigla: {_yaml_txt(aplicacao['sigla'])}
"""


# ---------------------------------------------------------------------------
# Sobras do template de worker
# ---------------------------------------------------------------------------

def sobras(raiz_infra: Path) -> list[Path]:
    """O que existe na infra e o EchoBridge nao usa."""
    return [raiz_infra / nome for nome in SOBRAS_DO_WORKER if (raiz_infra / nome).exists()]


def remover_sobras(raiz_infra: Path) -> list[Path]:
    """Apaga as sobras. Passa pela mesma barreira das escritas."""
    removidos = []
    for caminho in sobras(raiz_infra):
        alvo = _dentro_do_repositorio(caminho, raiz_infra)
        if alvo.is_dir():
            shutil.rmtree(alvo)
        else:
            alvo.unlink()
        removidos.append(alvo)
    return removidos


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------

def escrever_echobridge(
    project_root: Path,
    aplicacao: dict[str, Any],
    topicos: list[Topico],
    ambientes: list[AmbienteEcho],
) -> list[Path]:
    """Escreve a infra do EchoBridge e devolve os caminhos tocados."""
    raiz_infra = localizar_infra(project_root)
    raiz_repo = raiz_do_repositorio(raiz_infra)
    escritos: list[Path] = []

    marcadores = {
        "MODULE_REF": aplicacao["module_ref"],
        "SECRET_NAME": aplicacao["secret_name"],
        "GITHUB_REPO_ID": aplicacao["github_repo_id"],
        "GITHUB_REPO_NAME": aplicacao["github_repo_name"],
    }

    for nome in _VERBATIM:
        escritos.append(_gravar(raiz_infra / nome, raiz_repo, _ler_template(nome)))
    for nome in _COM_MARCADORES:
        conteudo = _aplicar(_ler_template(nome), marcadores)
        escritos.append(_gravar(raiz_infra / nome, raiz_repo, conteudo))

    # FIFO nao e pergunta: e uma propriedade do destino escolhido. Um ARN
    # terminado em ".fifo" e uma fila/topico FIFO, ponto.
    fifo = any(a.messaging_arn.endswith(".fifo") for a in ambientes)

    escritos.append(
        _gravar(raiz_infra / "locals.tf", raiz_repo, render_locals(aplicacao, topicos, fifo))
    )

    if aplicacao["usa_transformacao"]:
        escritos.append(
            _gravar(
                raiz_infra / "mappers" / "sink_transformation.json",
                raiz_repo,
                render_transformacao(topicos),
            )
        )

    for ambiente in ambientes:
        escritos.append(
            _gravar(
                raiz_infra / "inventories" / ambiente.nome / "terraform.tfvars",
                raiz_repo,
                render_tfvars(aplicacao, ambiente, topicos),
            )
        )

    escritos.append(
        _gravar(raiz_repo / ".iupipes.yml", raiz_repo, render_iupipes(aplicacao, ambientes))
    )

    return escritos


def _gravar(alvo: Path, raiz_repo: Path, conteudo: str) -> Path:
    caminho = _dentro_do_repositorio(alvo, raiz_repo)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" para o arquivo nao mudar de conteudo so por ter sido gerado
    # no Windows -- senao todo /infra aqui vira diff de CRLF.
    caminho.write_text(conteudo, encoding="utf-8", newline="\n")
    return caminho
