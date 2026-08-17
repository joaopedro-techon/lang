"""Catalogo DECLARATIVO de perguntas do wizard + validacao.

Por que este arquivo existe
---------------------------
O objetivo do /initialize e ser 100% deterministico: as mesmas respostas
sempre produzem a mesma spec, sem LLM no meio, sem alucinacao e sem drift.

A forma de conseguir isso e nao deixar as perguntas espalhadas por `input()`
no meio do codigo. Aqui elas viram DADOS: cada pergunta e um objeto `Question`
com o texto, as opcoes validas e as regras de validacao.

Isso da tres beneficios:

1. VALIDACAO UNICA. A funcao `validate()` e a unica fonte da verdade sobre o
   que e uma resposta valida. O terminal usa ela para reperguntar, e o grafo
   usa ela de novo para garantir o invariante. Um frontend web futuro usaria
   exatamente a mesma funcao.

2. FRONTEND-AGNOSTICO. `Question.to_dict()` devolve JSON puro. O grafo emite
   esse JSON quando precisa de uma resposta; quem renderiza (terminal hoje,
   web/Slack amanha) nao muda o grafo.

3. AUDITAVEL. Para saber exatamente o que o agente pergunta e o que ele
   aceita, basta ler este arquivo -- nao e preciso rastrear prompts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal


class ValidationError(ValueError):
    """Resposta invalida. A mensagem e mostrada direto ao usuario."""


# ---------------------------------------------------------------------------
# Estruturas
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Option:
    """Uma opcao selecionavel de uma pergunta de escolha.

    `available=False` NAO esconde nem bloqueia a opcao: o usuario ainda pode
    escolhe-la. Ela e apenas marcada como "em breve", e o grafo usa esse flag
    para encerrar o fluxo com uma mensagem explicando que a feature ainda nao
    existe. Foi essa a regra pedida para "App" e "Schedule".
    """

    value: str
    label: str
    description: str = ""
    available: bool = True
    note: str = ""  # explicacao mostrada quando available=False

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "label": self.label,
            "description": self.description,
            "available": self.available,
            "note": self.note,
        }

    @staticmethod
    def from_dict(dados: dict[str, Any]) -> Option:
        return Option(
            value=dados["value"],
            label=dados["label"],
            description=dados.get("description", ""),
            available=bool(dados.get("available", True)),
            note=dados.get("note", ""),
        )


Kind = Literal["choice", "multi_choice", "text", "integer", "confirm"]


@dataclass(frozen=True)
class Question:
    """Uma pergunta do wizard, com suas regras de validacao."""

    id: str
    kind: Kind
    title: str
    help: str = ""

    # choice / multi_choice
    options: tuple[Option, ...] = ()
    # multi_choice: pode terminar sem nada marcado?
    # text: enter vazio e uma resposta valida (devolve "")? Serve para os campos
    # que tem sugestao -- o no aceita o branco e usa o valor sugerido no `help`.
    allow_empty: bool = False

    # text
    pattern: str | None = None
    pattern_help: str = ""

    # integer
    min_value: int | None = None
    max_value: int | None = None

    def option(self, value: str) -> Option | None:
        """Devolve a Option com aquele `value`, ou None."""
        for opcao in self.options:
            if opcao.value == value:
                return opcao
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serializa para JSON puro (o payload que o grafo emite)."""
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "help": self.help,
            "options": [o.to_dict() for o in self.options],
            "allow_empty": self.allow_empty,
            "pattern": self.pattern,
            "pattern_help": self.pattern_help,
            "min_value": self.min_value,
            "max_value": self.max_value,
        }

    @staticmethod
    def from_dict(dados: dict[str, Any]) -> Question:
        """Reconstroi a pergunta a partir do JSON emitido pelo grafo.

        E isso que permite ao frontend chamar exatamente a mesma `validate()`
        que o grafo usa, sem reimplementar regra nenhuma.
        """
        return Question(
            id=dados["id"],
            kind=dados["kind"],
            title=dados["title"],
            help=dados.get("help", ""),
            options=tuple(Option.from_dict(o) for o in dados.get("options", ())),
            allow_empty=bool(dados.get("allow_empty", False)),
            pattern=dados.get("pattern"),
            pattern_help=dados.get("pattern_help", ""),
            min_value=dados.get("min_value"),
            max_value=dados.get("max_value"),
        )


# ---------------------------------------------------------------------------
# Validacao -- a fonte unica da verdade
# ---------------------------------------------------------------------------

def validate(pergunta: Question, valor: Any) -> Any:
    """Valida e normaliza `valor` para `pergunta`.

    Levanta ValidationError com uma mensagem legivel se for invalido.
    Devolve o valor ja normalizado (str limpa, int, list[str], bool).
    """
    if pergunta.kind == "choice":
        return _validar_escolha(pergunta, valor)
    if pergunta.kind == "multi_choice":
        return _validar_multi_escolha(pergunta, valor)
    if pergunta.kind == "text":
        return _validar_texto(pergunta, valor)
    if pergunta.kind == "integer":
        return _validar_inteiro(pergunta, valor)
    if pergunta.kind == "confirm":
        return _validar_confirmacao(valor)
    raise ValidationError(f"Tipo de pergunta desconhecido: {pergunta.kind}")


def _validar_escolha(pergunta: Question, valor: Any) -> str:
    if not isinstance(valor, str):
        raise ValidationError("Escolha invalida.")
    if pergunta.option(valor) is None:
        validas = ", ".join(o.value for o in pergunta.options)
        raise ValidationError(f"'{valor}' nao e uma opcao. Validas: {validas}.")
    return valor


def _validar_multi_escolha(pergunta: Question, valor: Any) -> list[str]:
    if valor is None:
        valor = []
    if not isinstance(valor, (list, tuple)):
        raise ValidationError("Esperava uma lista de opcoes.")

    escolhidos: list[str] = []
    for item in valor:
        if not isinstance(item, str) or pergunta.option(item) is None:
            validas = ", ".join(o.value for o in pergunta.options)
            raise ValidationError(f"'{item}' nao e uma opcao. Validas: {validas}.")
        if item not in escolhidos:  # remove duplicatas, preserva a ordem
            escolhidos.append(item)

    if not escolhidos and not pergunta.allow_empty:
        raise ValidationError("Selecione ao menos uma opcao.")

    # Ordena pela ordem do catalogo, para a spec ficar estavel:
    # as mesmas escolhas geram sempre o mesmo JSON.
    ordem = [o.value for o in pergunta.options]
    return sorted(escolhidos, key=ordem.index)


def _validar_texto(pergunta: Question, valor: Any) -> str:
    if not isinstance(valor, str):
        raise ValidationError("Esperava um texto.")
    texto = valor.strip()
    if not texto:
        if pergunta.allow_empty:
            return ""
        raise ValidationError("Nao pode ficar em branco.")
    if pergunta.pattern and not re.fullmatch(pergunta.pattern, texto):
        raise ValidationError(pergunta.pattern_help or f"Formato invalido: '{texto}'.")
    return texto


def _validar_inteiro(pergunta: Question, valor: Any) -> int:
    if isinstance(valor, bool):  # em Python bool e subclasse de int
        raise ValidationError("Esperava um numero inteiro.")
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto.lstrip("+-").isdigit():
            raise ValidationError(f"'{valor}' nao e um numero inteiro.")
        valor = int(texto)
    if not isinstance(valor, int):
        raise ValidationError("Esperava um numero inteiro.")
    if pergunta.min_value is not None and valor < pergunta.min_value:
        raise ValidationError(f"Deve ser no minimo {pergunta.min_value}.")
    if pergunta.max_value is not None and valor > pergunta.max_value:
        raise ValidationError(f"Deve ser no maximo {pergunta.max_value}.")
    return valor


def _validar_confirmacao(valor: Any) -> bool:
    if isinstance(valor, bool):
        return valor
    raise ValidationError("Esperava sim ou nao.")


# ---------------------------------------------------------------------------
# As perguntas do /initialize
# ---------------------------------------------------------------------------

# Passo 1 -- worker ou app.
# "app" fica selecionavel porem indisponivel: o grafo encerra com a nota.
Q_TIPO_PROJETO = Question(
    id="project_type",
    kind="choice",
    title="Que tipo de projeto voce vai criar?",
    options=(
        Option(
            value="worker",
            label="Worker",
            description="Processa mensagens de uma fila SQS ou roda de tempos em tempos. Sem API exposta.",
        ),
        Option(
            value="app",
            label="App",
            description="Expoe uma API REST atras de um load balancer.",
            available=False,
            note="O tipo 'App' (API REST com load balancer) ainda nao esta disponivel neste agente.",
        ),
    ),
)

# Passo 2 -- so acontece se o tipo for worker.
Q_GATILHO = Question(
    id="trigger",
    kind="choice",
    title="O que dispara o worker?",
    options=(
        Option(
            value="sqs",
            label="Consumo SQS",
            description="O worker fica consumindo mensagens de uma fila SQS.",
        ),
        Option(
            value="schedule",
            label="Schedule",
            description="O worker roda periodicamente (agendado).",
            available=False,
            note="O gatilho 'Schedule' (execucao agendada) ainda nao esta disponivel neste agente.",
        ),
    ),
)

# Nome de fila SQS conforme a AWS: ate 80 caracteres, alfanumericos, hifen e
# underscore. Filas FIFO terminam em ".fifo" (o sufixo conta no limite de 80).
_PADRAO_FILA_SQS = r"[A-Za-z0-9_-]{1,80}|[A-Za-z0-9_-]{1,75}\.fifo"

Q_FILA_SQS = Question(
    id="queue_name",
    kind="text",
    title="Qual o nome da fila SQS que o worker vai consumir?",
    help="Informe apenas o nome da fila, nao a URL nem o ARN.",
    pattern=_PADRAO_FILA_SQS,
    pattern_help=(
        "Nome de fila SQS invalido. Use ate 80 caracteres entre letras, numeros, "
        "hifen (-) e underscore (_). Filas FIFO terminam em '.fifo'."
    ),
)

Q_THROUGHPUT = Question(
    id="messages_per_second",
    kind="integer",
    title="Quantas mensagens por segundo o worker precisa processar?",
    help="Use a vazao esperada em pico. Isso vai dimensionar concorrencia e autoscaling.",
    min_value=1,
    max_value=100_000,
)

Q_DEPENDENCIAS = Question(
    id="dependencies",
    kind="multi_choice",
    title="Quais dependencias o projeto precisa?",
    help="Pode marcar varias, ou nenhuma.",
    allow_empty=True,
    options=(
        Option("dynamodb", "DynamoDB", "Banco NoSQL da AWS."),
        Option("firehose", "Firehose", "Kinesis Data Firehose, para streaming de eventos."),
        Option("sns", "SNS", "Simple Notification Service, para publicar mensagens."),
        Option("aurora-rds", "Aurora RDS", "Banco relacional gerenciado (via Spring Data JPA)."),
        Option("feign", "Feign", "Cliente HTTP declarativo (OpenFeign) para chamar outras APIs."),
    ),
)


# ---------------------------------------------------------------------------
# As perguntas do /infra
# ---------------------------------------------------------------------------
#
# Divididas em dois grupos, e a divisao importa para o wizard nao ficar
# insuportavel: o que descreve a APLICACAO e perguntado uma vez; so o que
# muda de ambiente para ambiente entra no loop.
#
# Tempo de processamento, concorrencia e porta do container sao propriedades
# do codigo, nao do ambiente -- por isso ficam no grupo de cima. A vazao fica
# no de baixo, porque dev e producao nao recebem a mesma carga.

_EMAIL = r"[^@\s]+@[^@\s]+\.[^@\s]+"
_NOME_RECURSO = r"[a-z0-9][a-z0-9-]{1,39}"

# O /infra tem um catalogo de tipos PROPRIO, separado do /initialize de
# proposito: o EchoBridge nao tem spec nem codigo para gerar -- ele so tem
# infra. Oferece-lo no /initialize prometeria um passo que nao existe.
Q_TIPO_INFRA = Question(
    id="project_type",
    kind="choice",
    title="Que tipo de infra voce vai configurar?",
    options=(
        Option(
            value="worker",
            label="Worker",
            description="Servico ECS proprio que consome uma fila SQS. Tem codigo, imagem e IAM no repositorio.",
        ),
        Option(
            value="echobridge",
            label="EchoBridge",
            description="Connector pronto que consome topicos Kafka e publica em SNS ou SQS. So infra: nao ha codigo no repositorio.",
        ),
        Option(
            value="app",
            label="App",
            description="Expoe uma API REST atras de um load balancer.",
            available=False,
            note="O tipo 'App' (API REST com load balancer) ainda nao esta disponivel neste agente.",
        ),
    ),
)

Q_AMBIENTES = Question(
    id="ambientes",
    kind="multi_choice",
    title="Quais ambientes voce quer configurar agora?",
    help="Cada um sera configurado separadamente, um de cada vez.",
    options=(
        Option("dev", "dev", "Perfil CUSTODIA-AI-DEV."),
        Option("hom", "hom", "Perfil CUSTODIA-AI-HOM."),
        Option("prod", "prod", "Perfil CUSTODIA-AI-PROD."),
    ),
)

# -- identidade da aplicacao (uma vez) --------------------------------------

Q_SIGLA = Question(
    id="sigla",
    kind="text",
    title="Qual a sigla da area?",
    help="Vai para as tags e para o nome da imagem no ECR. Ex.: SG2",
    pattern=r"[A-Za-z0-9]{2,10}",
    pattern_help="Use de 2 a 10 letras ou numeros, sem espaco. Ex.: SG2",
)

Q_SIGLA_APP = Question(
    id="sigla_app",
    kind="text",
    title="Qual a sigla-app (o codigo do aplicativo no inventario)?",
    pattern=r"[A-Za-z0-9-]{2,30}",
    pattern_help="Letras, numeros e hifen. Ex.: SG2-CUSTPV",
)

Q_PRODUTO = Question(
    id="produto",
    kind="text",
    title="Qual o nome do produto?",
    help="Ex.: Custodia de Ativos PF",
)

Q_CONTEXT = Question(
    id="context",
    kind="text",
    title="Qual o context da aplicacao?",
    pattern=_NOME_RECURSO,
    pattern_help="Minusculas, numeros e hifen. Ex.: custodia",
)

Q_SQUAD = Question(
    id="squad",
    kind="text",
    title="Qual o nome da squad?",
)

Q_FEATURE_NAME = Question(
    id="feature_name",
    kind="text",
    title="Qual o feature_name?",
    help="Entra no nome das roles e policies IAM. Ex.: custodia",
    pattern=_NOME_RECURSO,
    pattern_help="Minusculas, numeros e hifen, de 2 a 40 caracteres.",
)

Q_MICROSERVICE_NAME = Question(
    id="microservice_name",
    kind="text",
    title="Qual o microservice_name?",
    help="Entra no nome das roles, das policies e da imagem. Ex.: posvenda",
    pattern=_NOME_RECURSO,
    pattern_help="Minusculas, numeros e hifen, de 2 a 40 caracteres.",
)

Q_OWNER_EMAIL = Question(
    id="owner_email",
    kind="text",
    title="Qual o e-mail do time dono (owner_contact_email)?",
    pattern=_EMAIL,
    pattern_help="Informe um e-mail valido.",
)

Q_TECH_EMAIL = Question(
    id="tech_email",
    kind="text",
    title="Qual o e-mail do time tecnico (tech_team_email)?",
    pattern=_EMAIL,
    pattern_help="Informe um e-mail valido.",
)

Q_FINOPS_SQUAD = Question(
    id="finops_squad",
    kind="text",
    title="Qual o identificador da squad no FinOps?",
    help="Formato do inventario, com o codigo entre parenteses. Ex.: CUSTODIA (S123456)",
)

Q_FINOPS_PROJETO = Question(
    id="finops_projeto",
    kind="text",
    title="Qual o projeto, para rateio de FinOps?",
)

Q_FINOPS_OFERTA = Question(
    id="finops_oferta",
    kind="text",
    title="Qual a oferta, para rateio de FinOps?",
)

Q_FINOPS_SERVICO = Question(
    id="finops_servico",
    kind="text",
    title="Qual o servico de negocio, para rateio de FinOps?",
)

Q_PORTA_CONTAINER = Question(
    id="container_port",
    kind="integer",
    title="Em que porta o container escuta?",
    help="A mesma do server.port da aplicacao. O health check bate nela.",
    min_value=1,
    max_value=65535,
)

Q_TEMPO_PROCESSAMENTO = Question(
    id="tempo_ms",
    kind="integer",
    title="Quanto tempo o worker leva para processar UMA mensagem, em milissegundos?",
    help="Use a media em regime normal. Entra no calculo do autoscaling.",
    min_value=1,
    max_value=600_000,
)

Q_CONCORRENCIA = Question(
    id="concorrencia",
    kind="integer",
    title="Quantas mensagens uma task processa ao mesmo tempo?",
    help="A concorrencia do listener SQS. Entra no calculo do autoscaling.",
    min_value=1,
    max_value=1_000,
)

# -- por ambiente ------------------------------------------------------------

Q_STS_INTERNO = Question(
    id="sts_internal_url",
    kind="text",
    title="Qual a URL interna do STS neste ambiente?",
    pattern=r"https?://\S+",
    pattern_help="Informe uma URL comecando com http:// ou https://",
)

Q_STS_EXTERNO = Question(
    id="sts_external_url",
    kind="text",
    title="Qual a URL externa do STS neste ambiente?",
    pattern=r"https?://\S+",
    pattern_help="Informe uma URL comecando com http:// ou https://",
)


def pergunta_vazao(ambiente: str, sugestao: int | None) -> Question:
    """Vazao esperada NAQUELE ambiente.

    A spec do /initialize traz a vazao de pico do projeto; ela aparece como
    sugestao no enunciado, mas nao e assumida: dev quase nunca recebe a mesma
    carga de producao.
    """
    ajuda = "Use a vazao esperada em pico neste ambiente."
    if sugestao:
        ajuda += f" A spec do projeto registra {sugestao} msg/s no pico."
    return Question(
        id=f"vazao_{ambiente}",
        kind="integer",
        title=f"Quantas mensagens por segundo o worker processa em {ambiente}?",
        help=ajuda,
        min_value=1,
        max_value=100_000,
    )


# ---------------------------------------------------------------------------
# As perguntas do /infra -- ramo EchoBridge
# ---------------------------------------------------------------------------
#
# O EchoBridge nao e um worker: nao ha codigo Java no repositorio, nao ha
# imagem propria e nao ha IAM escrito a mao. O que existe e UM modulo terraform
# (`itau-hn8-modules-ecs-echobridge`) que sobe um connector pronto -- ele
# consome topicos Kafka e publica em SNS ou SQS. Configurar o projeto e, na
# pratica, preencher as variaveis desse modulo sem errar nenhuma.
#
# Por isso as perguntas daqui sao mais "de dominio" que as do worker: broker,
# particao, filtro de evento, transformacao de payload. Cada uma corresponde a
# um campo que o README do modulo marca como obrigatorio.

# O que o modulo aceita em `condition`, dentro de body/clazz/header.
CONDICOES_FILTRO: tuple[str, ...] = (
    "contains",
    "containsIgnoreCase",
    "lessThan",
    "lessThanOrEquals",
    "greaterThan",
    "greaterThanOrEquals",
    "startWith",
    "endWith",
    "notContains",
    "notContainsIgnoreCase",
    "notLessThan",
    "notLessThanOrEquals",
    "notGreaterThan",
    "notGreaterThanOrEquals",
    "notStartWith",
    "notEndWith",
)

# Perfis de recurso do `sink_task_profile_compute_config`, com a capacidade que
# o README publica. O RPS entra na descricao porque escolher o perfil e, no
# fundo, responder "quanta vazao este connector precisa aguentar" -- e sem o
# numero a lista vira quatro nomes sem significado.
PERFIS_COMPUTE: tuple[tuple[str, str, str], ...] = (
    (
        "MINIMUM_RESOURCE",
        "MINIMUM_RESOURCE",
        "0,5 vCPU · 1 GB · metaspace 128m · G1GC · paralelismo 1 · ate ~50 RPS (3 particoes)",
    ),
    (
        "MEDIUM_RESOURCE",
        "MEDIUM_RESOURCE",
        "1 vCPU · 2 GB · metaspace 256m · G1GC · paralelismo 1 · ate ~330 RPS (3 particoes)",
    ),
    (
        "LARGE_RESOURCE",
        "LARGE_RESOURCE",
        "2 vCPU · 4 GB · metaspace 512m · G1GC · paralelismo 2 · ate ~700 RPS (3 particoes)",
    ),
    (
        "CUSTOM_PROFILE",
        "CUSTOM_PROFILE",
        "Perfil customizado -- exige preencher os recursos a mao no tfvars depois.",
    ),
)

# Versoes de referencia. Sao SUGESTOES mostradas no enunciado, nunca assumidas:
# o modulo e a imagem evoluem, e chutar a versao errada quebra o terraform de
# um jeito que so aparece no pipeline.
MODULO_ECHOBRIDGE = "itau-corp/itau-hn8-modules-ecs-echobridge"
MODULO_REF_SUGERIDA = "v0.22.0"
IMAGEM_ECHOBRIDGE = (
    "itau-hn8-docker.artifactory.prod.aws.cloud.ihf/"
    "itau-corp-itau-hn8-container-kafka-sink-to-amazon-message-services"
)
IMAGEM_TAG_SUGERIDA = "v0.18.3-c0eaade"

Q_EB_COMUNIDADE = Question(
    id="comunidade",
    kind="choice",
    title="Qual a comunidade dona do connector?",
    help="Vai para o local `sink_comunidade`.",
    options=(
        Option("Custodia de Ativos", "Custodia de Ativos"),
        Option("__outro__", "Outra -- quero digitar", "Abre um campo de texto livre."),
    ),
)

Q_EB_COMUNIDADE_TEXTO = Question(
    id="comunidade_texto",
    kind="text",
    title="Qual o nome da comunidade?",
)

Q_EB_FINALIDADE = Question(
    id="finalidade",
    kind="choice",
    title="Qual a finalidade do projeto?",
    help="Vira a tag `finalidade` em todos os recursos.",
    options=(
        Option("modernizacao", "modernizacao", "Reescrita/migracao de algo que ja existe."),
        Option("sustentacao", "sustentacao", "Manutencao do que ja esta em producao."),
        Option("novo-negocio", "novo-negocio", "Capacidade nova."),
        Option("__outro__", "Outra -- quero digitar", "Abre um campo de texto livre."),
    ),
)

Q_EB_FINALIDADE_TEXTO = Question(
    id="finalidade_texto",
    kind="text",
    title="Qual a finalidade?",
    pattern=r"[A-Za-z0-9 _-]{2,40}",
    pattern_help="Letras, numeros, espaco, hifen e underscore, de 2 a 40 caracteres.",
)

Q_EB_EMPRESA = Question(
    id="empresa",
    kind="text",
    title="Qual o codigo da empresa, para o rateio de FinOps?",
    help="Tag `iu:finops:alocacao:empresa`. Enter aceita 341 (Itau Unibanco).",
    allow_empty=True,
    pattern=r"[0-9]{3,5}",
    pattern_help="Somente numeros, de 3 a 5 digitos. Ex.: 341",
)

Q_EB_PRODUTO_FINOPS = Question(
    id="produto_finops",
    kind="text",
    title="Qual o produto, para o rateio de FinOps?",
    help="Tag `iu:finops:alocacao:produto`. Ex.: acionar_e_Receber",
    pattern=r"[A-Za-z0-9_-]{2,40}",
    pattern_help="Letras, numeros, hifen e underscore, de 2 a 40 caracteres.",
)

Q_EB_DESTINO = Question(
    id="destino",
    kind="choice",
    title="Para onde o connector publica a mensagem?",
    help="Vai para o local `sink_messaging_service.type`.",
    options=(
        Option("SNS", "SNS", "Publica num topico -- varios assinantes recebem."),
        Option("SQS", "SQS", "Enfileira numa fila -- um consumidor por mensagem."),
    ),
)

Q_EB_TRANSFORMACAO = Question(
    id="usa_transformacao",
    kind="confirm",
    title="O payload precisa ser transformado antes de publicar?",
    help=(
        "Se sim, cada topico ganha um mapeamento em mappers/sink_transformation.json\n"
        "(renomear campos, achatar o envelope, injetar constantes).\n"
        "Se nao, a mensagem sai do Kafka e entra no destino como veio."
    ),
)

Q_EB_FILTRO = Question(
    id="usa_filtro",
    kind="confirm",
    title="O connector deve descartar parte dos eventos?",
    help=(
        "Se nao, TODO evento dos topicos escolhidos e publicado no destino.\n"
        "Se sim, cada topico pode ganhar um filtro por header, classe ou corpo."
    ),
)

Q_EB_QTD_TOPICOS = Question(
    id="qtd_topicos",
    kind="integer",
    title="Quantos topicos Kafka este connector vai consumir?",
    help="Cada um sera perguntado separadamente, um de cada vez.",
    min_value=1,
    max_value=20,
)

Q_EB_QTD_BROKERS = Question(
    id="qtd_brokers",
    kind="integer",
    title="Quantos clusters Kafka (bootstrap_servers) diferentes esses topicos usam?",
    help=(
        "Quase sempre 1. So passa disso quando os topicos vivem em brokers\n"
        "distintos -- o modulo agrupa os topicos por broker no tfvars."
    ),
    min_value=1,
    max_value=5,
)

Q_EB_MODULO_REF = Question(
    id="module_ref",
    kind="text",
    title="Qual a versao (tag) do modulo terraform do EchoBridge?",
    help=(
        f"Confira as releases em https://github.com/{MODULO_ECHOBRIDGE}\n"
        f"Enter aceita {MODULO_REF_SUGERIDA}."
    ),
    allow_empty=True,
    pattern=r"v?[0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9.-]*",
    pattern_help="Use o formato da tag do repositorio. Ex.: v0.22.0",
)

Q_EB_IMAGEM_TAG = Question(
    id="image_tag",
    kind="text",
    title="Qual a tag da imagem do connector (a que o .iupipes.yml publica)?",
    help=(
        f"Imagem: {IMAGEM_ECHOBRIDGE}\n"
        f"Enter aceita {IMAGEM_TAG_SUGERIDA}."
    ),
    allow_empty=True,
    pattern=r"[A-Za-z0-9][A-Za-z0-9._-]{0,60}",
    pattern_help="Use a tag publicada no Artifactory. Ex.: v0.18.3-c0eaade",
)

Q_EB_TOPICO_SCHEMA = Question(
    id="topico_schema",
    kind="choice",
    title="Este topico tem schema governado?",
    help=(
        "Governado vai para `sink_schema_topics_properties`; sem schema vai\n"
        "para `sink_schema_less_topics_properties`. O modulo trata os dois\n"
        "de forma diferente na desserializacao."
    ),
    options=(
        Option("governado", "Com schema governado", "Registrado no schema registry."),
        Option("sem", "Sem schema", "JSON solto, sem contrato registrado."),
    ),
)

Q_EB_LOG_LEVEL = Question(
    id="log_level",
    kind="choice",
    title="Qual o nivel de log neste ambiente?",
    options=(
        Option("INFO", "INFO", "O padrao. Use em dev e hom."),
        Option("WARN", "WARN", "So avisos e erros."),
        Option("ERROR", "ERROR", "So erros. Barato, mas cega o diagnostico."),
    ),
)


def pergunta_texto_com_sugestao(
    id_pergunta: str,
    titulo: str,
    sugestao: str,
    ajuda: str = "",
    pattern: str | None = None,
    pattern_help: str = "",
) -> Question:
    """Campo de texto em que o enter aceita a sugestao.

    O EchoBridge tem varios campos cujo valor segue uma convencao (o client_id
    do Kafka, o nome do repositorio, o group_id). Perguntar sem sugerir faria o
    dev digitar a convencao de cabeca -- e errar o sufixo do ambiente uma vez
    em tres. Perguntar com sugestao e ACEITAR o branco resolve os dois lados:
    quem segue a convencao aperta enter, quem tem um caso diferente digita.
    """
    linhas = [ajuda] if ajuda else []
    linhas.append(f"Enter aceita: {sugestao}")
    return Question(
        id=id_pergunta,
        kind="text",
        title=titulo,
        help="\n".join(linhas),
        allow_empty=True,
        pattern=pattern,
        pattern_help=pattern_help,
    )


def pergunta_condicao(id_pergunta: str, titulo: str, ajuda: str = "") -> Question:
    """Escolha de `condition` para um criterio de filtro."""
    return Question(
        id=id_pergunta,
        kind="choice",
        title=titulo,
        help=ajuda or "O modulo compara o valor do evento com os valores do filtro.",
        options=tuple(Option(c, c) for c in CONDICOES_FILTRO),
    )


def pergunta_perfil_compute(ambiente: str) -> Question:
    """Perfil de vCPU/memoria da task, naquele ambiente."""
    return Question(
        id=f"profile_{ambiente}",
        kind="choice",
        title=f"[{ambiente}] Qual o perfil de recursos da task?",
        help="Vai para `profile` no tfvars, dentro de sink_task_profile_compute_config.",
        options=tuple(Option(v, r, d) for v, r, d in PERFIS_COMPUTE),
    )


def pergunta_confirmacao(resumo: str) -> Question:
    """Monta a pergunta final de confirmacao.

    E a unica pergunta construida em runtime, porque o texto depende das
    respostas anteriores.
    """
    return Question(
        id="confirm",
        kind="confirm",
        title="Confirma e salva esta configuracao?",
        help=resumo,
    )
