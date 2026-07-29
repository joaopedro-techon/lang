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
    allow_empty: bool = False  # multi_choice pode terminar sem nada marcado?

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
