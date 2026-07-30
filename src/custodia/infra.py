"""O comando /infra: grafo LangGraph 100% deterministico.

Nao ha LLM aqui, pelo mesmo motivo do /initialize: isto decide infraestrutura
de verdade. Se o agente "inventar" uma subnet, alguem sobe um servico na rede
errada. Toda opcao oferecida vem da AWS ou de uma pergunta; nada e inferido.

O fluxo
-------

    START
      |
      v
    app ou worker? ------ "app" ----------> END  (feature indisponivel)
      | "worker"
      v
    quais ambientes? (dev/hom/prod)
      |
      v
    conferir TODOS os perfis --- algum quebrado ---> END (relatorio completo)
      |   valida antes de qualquer outra pergunta; um perfil de prod
      |   quebrado nao pode aparecer so depois da rodada de dev
      v
    confirmar contas ---------- "nao" --------------> END (cancelado)
      |   mostra em que conta cada ambiente caiu
      v
    identidade da aplicacao (sigla, produto, squad, emails, ...)
      |
      v
    +-> um ambiente por vez: cluster, vpc, subnets, cidrs, filas, vazao, STS
    |     |
    +-----+ ainda falta ambiente?
      |
      v
    revisar --- "nao" --> END  (cancelado)
      | "sim"
      v
    escrever infra/terraform  ------------> END

Duas regras de construcao
-------------------------
1. UM `interrupt()` por no, sem efeito colateral antes dele. Um no que pausa
   RODA DE NOVO inteiro quando o grafo e retomado (a mesma pegadinha descrita
   em `initialize.py`).
2. Nenhuma chamada de AWS num no que tem `interrupt()`. Se estivessem juntas,
   cada retomada refaria as consultas -- lento, e chamada de rede repetida
   toda vez que o dev responde uma pergunta.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from . import aws
from .dimensionamento import calcular
from .questions import (
    Q_AMBIENTES,
    Q_CONCORRENCIA,
    Q_CONTEXT,
    Q_FEATURE_NAME,
    Q_FINOPS_OFERTA,
    Q_FINOPS_PROJETO,
    Q_FINOPS_SERVICO,
    Q_FINOPS_SQUAD,
    Q_MICROSERVICE_NAME,
    Q_OWNER_EMAIL,
    Q_PORTA_CONTAINER,
    Q_PRODUTO,
    Q_SIGLA,
    Q_SIGLA_APP,
    Q_SQUAD,
    Q_STS_EXTERNO,
    Q_STS_INTERNO,
    Q_TECH_EMAIL,
    Q_TEMPO_PROCESSAMENTO,
    Option,
    Question,
    pergunta_confirmacao,
    pergunta_vazao,
    validate,
)
from .terraform import Ambiente, escrever_infra

STATUS_BLOQUEADO = "blocked"
STATUS_CANCELADO = "cancelled"
STATUS_ESCRITO = "written"
STATUS_ERRO_AWS = "aws_error"

# Cada par vira um no do grafo. A ordem aqui e a ordem das perguntas.
PERGUNTAS_DA_APLICACAO: tuple[tuple[str, Question], ...] = (
    ("sigla", Q_SIGLA),
    ("sigla_app", Q_SIGLA_APP),
    ("produto", Q_PRODUTO),
    ("context", Q_CONTEXT),
    ("squad", Q_SQUAD),
    ("feature_name", Q_FEATURE_NAME),
    ("microservice_name", Q_MICROSERVICE_NAME),
    ("owner_email", Q_OWNER_EMAIL),
    ("tech_email", Q_TECH_EMAIL),
    ("finops_squad", Q_FINOPS_SQUAD),
    ("finops_projeto", Q_FINOPS_PROJETO),
    ("finops_oferta", Q_FINOPS_OFERTA),
    ("finops_servico", Q_FINOPS_SERVICO),
    ("container_port", Q_PORTA_CONTAINER),
    ("tempo_ms", Q_TEMPO_PROCESSAMENTO),
    ("concorrencia", Q_CONCORRENCIA),
)


class InfraState(TypedDict, total=False):
    project_root: str
    sugestao_vazao: int          # vazao registrada na spec, se houver

    project_type: str
    ambientes: list[str]         # os que o dev escolheu
    aplicacao: dict[str, Any]    # respostas que valem para o projeto inteiro

    conferencia: list[str]       # relatorio dos perfis, linha a linha
    contas: dict[str, Any]       # conta/regiao por ambiente, ja conferidas

    indice: int                  # ambiente sendo configurado agora
    opcoes: dict[str, Any]       # listas vindas da AWS para o ambiente atual
    atual: dict[str, Any]        # respostas do ambiente atual
    coletados: list[dict[str, Any]]

    status: str
    message: str
    escritos: list[str]


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------

def _perguntar(pergunta: Question) -> Any:
    """Pausa o grafo, entrega a pergunta ao frontend e valida o que voltou."""
    resposta = interrupt(pergunta.to_dict())
    return validate(pergunta, resposta)


def _ambiente_atual(state: InfraState) -> str:
    return state["ambientes"][state.get("indice", 0)]


def _escolher_ou_digitar(
    id_pergunta: str,
    titulo: str,
    opcoes: list[Option],
    ajuda: str = "",
    vazio: str = "",
) -> Question:
    """Vira uma lista quando a AWS devolveu opcoes; um campo de texto quando nao.

    A consulta pode voltar vazia por motivo legitimo -- conta nova, ou o perfil
    sem permissao de listar. Travar o wizard nesse caso seria pior do que
    deixar o dev digitar o valor que ele ja conhece.
    """
    if opcoes:
        return Question(
            id=id_pergunta, kind="choice", title=titulo, help=ajuda, options=tuple(opcoes)
        )
    return Question(
        id=id_pergunta,
        kind="text",
        title=titulo,
        help=(ajuda + "\n" + vazio).strip(),
    )


def _com_aws(state: InfraState, tarefa: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    """Roda uma consulta na AWS traduzindo a falha em fim de fluxo legivel."""
    perfil = aws.perfil_do_ambiente(_ambiente_atual(state))
    try:
        return tarefa(perfil)
    except aws.AwsIndisponivel as exc:
        return {"status": STATUS_ERRO_AWS, "message": str(exc)}


def _rota_disponibilidade(state: InfraState) -> str:
    return "parar" if state.get("status") == STATUS_BLOQUEADO else "continuar"


def _rota_aws(state: InfraState) -> str:
    return "parar" if state.get("status") == STATUS_ERRO_AWS else "continuar"


# ---------------------------------------------------------------------------
# Nos: inicio
# ---------------------------------------------------------------------------

def no_tipo_projeto(state: InfraState) -> dict[str, Any]:
    """Worker ou app? App ainda nao existe -- mesma regra do /initialize."""
    from .questions import Q_TIPO_PROJETO

    escolha = _perguntar(Q_TIPO_PROJETO)
    opcao = Q_TIPO_PROJETO.option(escolha)
    if opcao is not None and not opcao.available:
        return {
            "project_type": escolha,
            "status": STATUS_BLOQUEADO,
            "message": (
                "A infra do tipo 'App' (API REST com load balancer) ainda nao esta "
                "disponivel neste agente."
            ),
        }
    return {"project_type": escolha}


def no_ambientes(state: InfraState) -> dict[str, Any]:
    """Quais ambientes configurar. Cada um vira uma volta no loop."""
    return {"ambientes": _perguntar(Q_AMBIENTES), "indice": 0, "coletados": []}


def no_validar_perfis(state: InfraState) -> dict[str, Any]:
    """Confere os perfis de TODOS os ambientes escolhidos, antes de perguntar.

    Sem isto, so o primeiro ambiente seria validado no inicio: um perfil de
    prod quebrado so apareceria depois das 17 perguntas de identidade e da
    rodada inteira de dev. Aqui o dev descobre tudo de uma vez, e conserta o
    ~/.aws de uma vez.

    Nao tem `interrupt()` -- e uma sequencia de chamadas de rede.
    """
    resultados = aws.conferir_perfis(state.get("ambientes", []))
    falhas = [r for r in resultados if not r.ok]

    if falhas:
        relatorio = "\n".join(r.linha() for r in resultados)
        return {
            "status": STATUS_ERRO_AWS,
            "message": (
                "Nem todos os perfis estao prontos:\n\n"
                f"{relatorio}\n\n"
                "Ajuste o ~/.aws e rode /infra de novo."
            ),
        }

    # Guarda conta/regiao por ambiente: o loop usa depois, sem consultar de novo.
    contas = {r.ambiente: {"conta": r.conta, "regiao": r.regiao} for r in resultados}

    def tarefa(perfil: str) -> dict[str, Any]:
        return {"opcoes": {"secrets": aws.listar_secrets(perfil)}}

    resultado = _com_aws(state, tarefa)
    if resultado.get("status") == STATUS_ERRO_AWS:
        return resultado

    return {**resultado, "conferencia": [r.linha() for r in resultados], "contas": contas}


def no_confirmar_perfis(state: InfraState) -> dict[str, Any]:
    """Mostra em que conta cada ambiente caiu e pede o aval.

    E o unico momento em que da para pegar "o perfil de prod aponta para a
    conta de dev" ANTES de escrever qualquer coisa. Custa um enter.
    """
    linhas = list(state.get("conferencia", []))
    repetidas = aws.contas_repetidas(
        [
            aws.Conferencia(ambiente=amb, perfil="", ok=True, conta=dados["conta"])
            for amb, dados in state.get("contas", {}).items()
        ]
    )
    texto = "Perfis conferidos:\n\n" + "\n".join(linhas)
    if repetidas:
        for conta, ambientes in repetidas.items():
            texto += (
                f"\n\n  ATENCAO: {' e '.join(ambientes)} apontam para a MESMA "
                f"conta ({conta})."
            )

    pergunta = pergunta_confirmacao(texto)
    if not _perguntar(
        Question(
            id="confirmar_perfis",
            kind="confirm",
            title="Seguir com estes ambientes?",
            help=pergunta.help,
        )
    ):
        return {
            "status": STATUS_CANCELADO,
            "message": "Nada foi escrito. Ajuste os perfis e rode /infra de novo.",
        }
    return {}


def _rota_confirmar_perfis(state: InfraState) -> str:
    return "parar" if state.get("status") == STATUS_CANCELADO else "continuar"


def _no_de_pergunta(campo: str, pergunta: Question) -> Callable[[InfraState], dict[str, Any]]:
    """Fabrica um no que faz UMA pergunta e guarda a resposta em `aplicacao`."""

    def no(state: InfraState) -> dict[str, Any]:
        respostas = dict(state.get("aplicacao", {}))
        respostas[campo] = _perguntar(pergunta)
        return {"aplicacao": respostas}

    return no


def no_secret(state: InfraState) -> dict[str, Any]:
    """Nome do secret com as credenciais STS (vai para o data.tf)."""
    nomes = state.get("opcoes", {}).get("secrets", [])
    pergunta = _escolher_ou_digitar(
        "secret_name",
        "Qual o secret com as credenciais STS da aplicacao?",
        [Option(n, n) for n in nomes],
        ajuda="O data.tf le client_id e client_secret dele.",
        vazio="Nenhum secret foi listado pelo perfil. Informe o nome completo.",
    )
    respostas = dict(state.get("aplicacao", {}))
    respostas["secret_name"] = _perguntar(pergunta)
    return {"aplicacao": respostas}


# ---------------------------------------------------------------------------
# Nos: o loop por ambiente
# ---------------------------------------------------------------------------

def no_conectar_ambiente(state: InfraState) -> dict[str, Any]:
    """Carrega, de uma vez, tudo o que o ambiente atual precisa listar."""

    # Conta e regiao ja foram conferidas na entrada; nao consultamos de novo.
    ja_conferido = state.get("contas", {}).get(_ambiente_atual(state), {})

    def tarefa(perfil: str) -> dict[str, Any]:
        return {
            "opcoes": {
                # Campos de exibicao: ausencia nao pode derrubar o wizard.
                "conta": ja_conferido.get("conta", "?"),
                "regiao": ja_conferido.get("regiao", "?"),
                "perfil": perfil,
                "clusters": aws.listar_clusters_ecs(perfil),
                "vpcs": aws.listar_vpcs(perfil),
                "filas": aws.listar_filas_sqs(perfil),
                "subnets": [],
            },
            "atual": {},
        }

    return _com_aws(state, tarefa)


def _de_onde(state: InfraState) -> str:
    """Perfil, conta e regiao que estao respondendo as listagens.

    Aparece na primeira pergunta de cada ambiente porque regiao errada nao da
    erro -- devolve lista vazia. Ver a regiao na tela e o que separa "esta
    conta nao tem cluster nenhum" de "estou olhando para a regiao errada".
    """
    opcoes = state.get("opcoes", {})
    return (
        f"Perfil {opcoes.get('perfil', '?')} · conta {opcoes.get('conta', '?')} · "
        f"regiao {opcoes.get('regiao', '?')}"
    )


def no_cluster(state: InfraState) -> dict[str, Any]:
    ambiente = _ambiente_atual(state)
    nomes = state.get("opcoes", {}).get("clusters", [])
    pergunta = _escolher_ou_digitar(
        "ecs_cluster_name",
        f"[{ambiente}] Em qual cluster ECS o worker vai rodar?",
        [Option(n, n) for n in nomes],
        ajuda=_de_onde(state),
        vazio="Nenhum cluster foi listado nesta conta/regiao. Informe o nome.",
    )
    return {"atual": {**state.get("atual", {}), "ecs_cluster_name": _perguntar(pergunta)}}


def no_vpc(state: InfraState) -> dict[str, Any]:
    ambiente = _ambiente_atual(state)
    vpcs = state.get("opcoes", {}).get("vpcs", [])
    pergunta = _escolher_ou_digitar(
        "service_vpc_id",
        f"[{ambiente}] Em qual VPC?",
        [Option(v["id"], f"{v['id']}  {v['nome']}", v["cidr"]) for v in vpcs],
        vazio="Nenhuma VPC foi listada. Informe o vpc-id.",
    )
    return {"atual": {**state.get("atual", {}), "service_vpc_id": _perguntar(pergunta)}}


def no_carregar_subnets(state: InfraState) -> dict[str, Any]:
    """Consulta as subnets da VPC escolhida. Sem interrupt: e chamada de rede."""
    vpc_id = state.get("atual", {}).get("service_vpc_id", "")

    def tarefa(perfil: str) -> dict[str, Any]:
        opcoes = dict(state.get("opcoes", {}))
        opcoes["subnets"] = aws.listar_subnets(perfil, vpc_id)
        return {"opcoes": opcoes}

    return _com_aws(state, tarefa)


def no_subnets(state: InfraState) -> dict[str, Any]:
    ambiente = _ambiente_atual(state)
    subnets = state.get("opcoes", {}).get("subnets", [])
    if subnets:
        pergunta = Question(
            id="service_subnets",
            kind="multi_choice",
            title=f"[{ambiente}] Em quais subnets o servico vai rodar?",
            help="Escolha uma por zona de disponibilidade, quando possivel.",
            options=tuple(
                Option(s["id"], f"{s['id']}  {s['az']}", f"{s['cidr']}  {s['nome']}")
                for s in subnets
            ),
        )
        return {"atual": {**state.get("atual", {}), "service_subnets": _perguntar(pergunta)}}

    # Sem listagem, cai para texto separado por virgula.
    pergunta = Question(
        id="service_subnets",
        kind="text",
        title=f"[{ambiente}] Quais subnets? (separe por virgula)",
        help="Nenhuma subnet foi listada pelo perfil.",
    )
    bruto = _perguntar(pergunta)
    ids = [p.strip() for p in bruto.split(",") if p.strip()]
    return {"atual": {**state.get("atual", {}), "service_subnets": ids}}


def no_cidrs(state: InfraState) -> dict[str, Any]:
    """CIDRs liberados, montados a partir das subnets escolhidas.

    Nao ha consulta nova: `listar_subnets` ja trouxe o CIDR de cada subnet.
    """
    ambiente = _ambiente_atual(state)
    escolhidas = set(state.get("atual", {}).get("service_subnets", []))
    subnets = state.get("opcoes", {}).get("subnets", [])
    cidrs = [s["cidr"] for s in subnets if s["id"] in escolhidas and s.get("cidr")]

    if cidrs:
        pergunta = Question(
            id="service_cidr_blocks",
            kind="multi_choice",
            title=f"[{ambiente}] Quais CIDRs liberar no security group?",
            help="Sao os CIDRs das subnets que voce acabou de escolher.",
            options=tuple(Option(c, c) for c in cidrs),
        )
        return {
            "atual": {**state.get("atual", {}), "service_cidr_blocks": _perguntar(pergunta)}
        }

    pergunta = Question(
        id="service_cidr_blocks",
        kind="text",
        title=f"[{ambiente}] Quais CIDRs liberar? (separe por virgula)",
        help="Nao consegui derivar os CIDRs das subnets escolhidas.",
    )
    bruto = _perguntar(pergunta)
    blocos = [p.strip() for p in bruto.split(",") if p.strip()]
    return {"atual": {**state.get("atual", {}), "service_cidr_blocks": blocos}}


def no_filas(state: InfraState) -> dict[str, Any]:
    """Filas observadas pelo autoscaling."""
    ambiente = _ambiente_atual(state)
    filas = state.get("opcoes", {}).get("filas", [])
    if filas:
        pergunta = Question(
            id="queue_names",
            kind="multi_choice",
            title=f"[{ambiente}] Quais filas o autoscaling deve observar?",
            help="O backlog delas e o sinal que sobe e desce tasks.",
            options=tuple(Option(f, f) for f in filas),
        )
        return {"atual": {**state.get("atual", {}), "queue_names": _perguntar(pergunta)}}

    pergunta = Question(
        id="queue_names",
        kind="text",
        title=f"[{ambiente}] Quais filas o autoscaling deve observar? (separe por virgula)",
        help="Nenhuma fila foi listada pelo perfil.",
    )
    bruto = _perguntar(pergunta)
    nomes = [p.strip() for p in bruto.split(",") if p.strip()]
    return {"atual": {**state.get("atual", {}), "queue_names": nomes}}


def no_vazao(state: InfraState) -> dict[str, Any]:
    ambiente = _ambiente_atual(state)
    pergunta = pergunta_vazao(ambiente, state.get("sugestao_vazao"))
    return {"atual": {**state.get("atual", {}), "vazao": _perguntar(pergunta)}}


def no_sts_interno(state: InfraState) -> dict[str, Any]:
    return {
        "atual": {**state.get("atual", {}), "sts_internal_url": _perguntar(Q_STS_INTERNO)}
    }


def no_sts_externo(state: InfraState) -> dict[str, Any]:
    return {
        "atual": {**state.get("atual", {}), "sts_external_url": _perguntar(Q_STS_EXTERNO)}
    }


def no_fechar_ambiente(state: InfraState) -> dict[str, Any]:
    """Fecha o ambiente atual e avanca o indice. Sem interrupt e sem escrita."""
    coletados = list(state.get("coletados", []))
    coletados.append({"nome": _ambiente_atual(state), **state.get("atual", {})})
    return {"coletados": coletados, "indice": state.get("indice", 0) + 1, "atual": {}}


def _rota_proximo_ambiente(state: InfraState) -> str:
    if state.get("status") == STATUS_ERRO_AWS:
        return "parar"
    return "proximo" if state.get("indice", 0) < len(state.get("ambientes", [])) else "revisar"


# ---------------------------------------------------------------------------
# Nos: fim
# ---------------------------------------------------------------------------

def resumo(state: InfraState) -> str:
    """Texto da revisao: o que vai ser escrito, antes de escrever."""
    app = state.get("aplicacao", {})
    linhas = [
        f"  Projeto      : {state.get('project_root', '-')}",
        f"  Aplicacao    : {app.get('sigla', '?')}-{app.get('feature_name', '?')}"
        f"-{app.get('microservice_name', '?')}",
        f"  Secret STS   : {app.get('secret_name', '-')}",
        f"  Porta        : {app.get('container_port', '-')}",
        f"  Processamento: {app.get('tempo_ms', '-')}ms por msg, "
        f"concorrencia {app.get('concorrencia', '-')}",
        "",
    ]
    for ambiente in state.get("coletados", []):
        dim = calcular(
            ambiente["vazao"], app.get("tempo_ms", 1), app.get("concorrencia", 1)
        )
        linhas += [
            f"  [{ambiente['nome']}]",
            f"    cluster   : {ambiente['ecs_cluster_name']}",
            f"    vpc       : {ambiente['service_vpc_id']}",
            f"    subnets   : {', '.join(ambiente['service_subnets']) or '-'}",
            f"    cidrs     : {', '.join(ambiente['service_cidr_blocks']) or '-'}",
            f"    filas     : {', '.join(ambiente['queue_names']) or '-'}",
            f"    vazao     : {ambiente['vazao']} msg/s",
            f"    {dim.explicar()}",
            "",
        ]
    return "\n".join(linhas)


def no_revisar(state: InfraState) -> dict[str, Any]:
    """Ultima chance antes de qualquer escrita em disco."""
    texto = resumo(state) + (
        "\n  Os arquivos de infra/terraform serao SOBRESCRITOS "
        "(ambientes nao escolhidos ficam intactos)."
    )
    if not _perguntar(pergunta_confirmacao(texto)):
        return {
            "status": STATUS_CANCELADO,
            "message": "Nada foi escrito. Rode /infra de novo quando quiser.",
        }
    return {}


def _rota_confirmacao(state: InfraState) -> str:
    return "parar" if state.get("status") == STATUS_CANCELADO else "escrever"


def no_escrever(state: InfraState) -> dict[str, Any]:
    """Unico no que escreve em disco -- e, por isso, unico sem `interrupt()`."""
    app = state.get("aplicacao", {})
    identidade = {
        **app,
        # A tag de FinOps usa o produto em formato de slug.
        "finops_produto": app.get("produto", "").replace(" ", "-"),
    }

    ambientes = [
        Ambiente(
            nome=a["nome"],
            ecs_cluster_name=a["ecs_cluster_name"],
            vpc_id=a["service_vpc_id"],
            subnets=a["service_subnets"],
            cidr_blocks=a["service_cidr_blocks"],
            container_port=app["container_port"],
            queue_names=a["queue_names"],
            sts_internal_url=a["sts_internal_url"],
            sts_external_url=a["sts_external_url"],
            dimensionamento=calcular(a["vazao"], app["tempo_ms"], app["concorrencia"]),
        )
        for a in state.get("coletados", [])
    ]

    try:
        escritos = escrever_infra(Path(state["project_root"]), identidade, ambientes)
    except (OSError, PermissionError, KeyError, RuntimeError) as exc:
        return {"status": STATUS_ERRO_AWS, "message": f"falha ao escrever a infra: {exc}"}

    return {
        "status": STATUS_ESCRITO,
        "escritos": [str(c) for c in escritos],
        "message": "Infra escrita.",
    }


# ---------------------------------------------------------------------------
# Montagem do grafo
# ---------------------------------------------------------------------------

def build_infra_graph():
    grafo = StateGraph(InfraState)

    grafo.add_node("tipo_projeto", no_tipo_projeto)
    grafo.add_node("ambientes", no_ambientes)
    grafo.add_node("validar_perfis", no_validar_perfis)
    grafo.add_node("confirmar_perfis", no_confirmar_perfis)
    for campo, pergunta in PERGUNTAS_DA_APLICACAO:
        grafo.add_node(f"app_{campo}", _no_de_pergunta(campo, pergunta))
    grafo.add_node("secret", no_secret)

    grafo.add_node("conectar_ambiente", no_conectar_ambiente)
    grafo.add_node("cluster", no_cluster)
    grafo.add_node("vpc", no_vpc)
    grafo.add_node("carregar_subnets", no_carregar_subnets)
    grafo.add_node("subnets", no_subnets)
    grafo.add_node("cidrs", no_cidrs)
    grafo.add_node("filas", no_filas)
    grafo.add_node("vazao", no_vazao)
    grafo.add_node("sts_interno", no_sts_interno)
    grafo.add_node("sts_externo", no_sts_externo)
    grafo.add_node("fechar_ambiente", no_fechar_ambiente)

    grafo.add_node("revisar", no_revisar)
    grafo.add_node("escrever", no_escrever)

    grafo.add_edge(START, "tipo_projeto")
    grafo.add_conditional_edges(
        "tipo_projeto", _rota_disponibilidade, {"continuar": "ambientes", "parar": END}
    )
    grafo.add_edge("ambientes", "validar_perfis")

    # Perfil quebrado encerra aqui, antes de qualquer outra pergunta.
    grafo.add_conditional_edges(
        "validar_perfis",
        _rota_aws,
        {"continuar": "confirmar_perfis", "parar": END},
    )
    primeiro_campo = PERGUNTAS_DA_APLICACAO[0][0]
    grafo.add_conditional_edges(
        "confirmar_perfis",
        _rota_confirmar_perfis,
        {"continuar": f"app_{primeiro_campo}", "parar": END},
    )

    # As perguntas da aplicacao sao uma fila reta.
    for (campo, _), (proximo, _) in zip(
        PERGUNTAS_DA_APLICACAO, PERGUNTAS_DA_APLICACAO[1:]
    ):
        grafo.add_edge(f"app_{campo}", f"app_{proximo}")
    grafo.add_edge(f"app_{PERGUNTAS_DA_APLICACAO[-1][0]}", "secret")
    grafo.add_edge("secret", "conectar_ambiente")

    grafo.add_conditional_edges(
        "conectar_ambiente", _rota_aws, {"continuar": "cluster", "parar": END}
    )
    grafo.add_edge("cluster", "vpc")
    grafo.add_edge("vpc", "carregar_subnets")
    grafo.add_conditional_edges(
        "carregar_subnets", _rota_aws, {"continuar": "subnets", "parar": END}
    )
    grafo.add_edge("subnets", "cidrs")
    grafo.add_edge("cidrs", "filas")
    grafo.add_edge("filas", "vazao")
    grafo.add_edge("vazao", "sts_interno")
    grafo.add_edge("sts_interno", "sts_externo")
    grafo.add_edge("sts_externo", "fechar_ambiente")

    # O ciclo: volta para conectar_ambiente enquanto sobrar ambiente.
    grafo.add_conditional_edges(
        "fechar_ambiente",
        _rota_proximo_ambiente,
        {"proximo": "conectar_ambiente", "revisar": "revisar", "parar": END},
    )

    grafo.add_conditional_edges(
        "revisar", _rota_confirmacao, {"escrever": "escrever", "parar": END}
    )
    grafo.add_edge("escrever", END)

    return grafo.compile(checkpointer=MemorySaver())
