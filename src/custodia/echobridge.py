"""O ramo EchoBridge do /infra: grafo LangGraph 100% deterministico.

Nao ha LLM aqui, pelo mesmo motivo do resto do /infra: isto decide
infraestrutura de verdade. Toda opcao oferecida vem da AWS ou de uma pergunta;
nada e inferido -- exceto duas derivacoes que sao formato fixo da AWS e nao
opiniao (o ARN de uma fila SQS e o `.fifo` no fim de um ARN).

O que o EchoBridge e
--------------------
Um connector pronto: consome topicos Kafka e publica em SNS ou SQS. O
repositorio do time nao tem codigo -- tem so um modulo terraform apontado para
`itau-hn8-modules-ecs-echobridge`. Configurar o projeto e preencher as
variaveis desse modulo sem errar nenhuma, e e exatamente isso que este grafo
faz.

O fluxo
-------

    (vem do /infra, ja com ambientes escolhidos e perfis conferidos)
      |
      v
    identidade da aplicacao (comunidade, sigla, squad, emails, repo, secret)
      |
      v
    o que o connector faz (destino SNS/SQS, transforma?, filtra?, versoes)
      |
      v
    +-> um topico por vez: nome, broker, schema, filtro, mapeamento
    |     |
    +-----+ ainda falta topico?
      |
      v
    +-> um ambiente por vez: cluster, perfil, rede, kafka
    |     |
    |     +-> particoes de um topico  <-+   (ciclo dentro do ciclo:
    |     |         |                   |    o mesmo topico tem contagens
    |     |         +-------------------+    diferentes em dev e em prod)
    |     v
    |   destino, log
    |     |
    +-----+ ainda falta ambiente?
      |
      v
    revisar --- "nao" --> END  (cancelado)
      | "sim"
      v
    escrever infra/terraform + .iupipes.yml ------> END

Tres regras de construcao
-------------------------
1. UM `interrupt()` por no, sem efeito colateral antes dele. Um no que pausa
   RODA DE NOVO inteiro quando o grafo e retomado.
2. Nenhuma chamada de AWS num no que tem `interrupt()`. Se estivessem juntas,
   cada retomada refaria as consultas.
3. PERGUNTA CONDICIONAL E NO QUE DESISTE, nao aresta condicional. Metade das
   perguntas daqui so existe em certos casos (filtro por header so se o dev
   pediu filtro; mapeamento so se pediu transformacao). Modelar isso com
   arestas exigiria umas quinze rotas para pular de um no ao proximo
   aplicavel -- e cada rota nova e uma chance de pular o no errado. Em vez
   disso, a cadeia e RETA e o proprio no decide: se nao ha o que perguntar,
   devolve `{}` sem chamar `interrupt()`. Zero ou um interrupt por no continua
   valendo; o custo de um no que nao pergunta e uma volta do grafo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END

from . import aws
from .echobridge_tf import (
    AmbienteEcho,
    Topico,
    escrever_echobridge,
    remover_sobras,
    sobras,
)
from .questions import (
    IMAGEM_TAG_SUGERIDA,
    MODULO_REF_SUGERIDA,
    Option,
    Q_CONTEXT,
    Q_EB_COMUNIDADE,
    Q_EB_COMUNIDADE_TEXTO,
    Q_EB_DESTINO,
    Q_EB_EMPRESA,
    Q_EB_FILTRO,
    Q_EB_FINALIDADE,
    Q_EB_FINALIDADE_TEXTO,
    Q_EB_IMAGEM_TAG,
    Q_EB_LOG_LEVEL,
    Q_EB_MODULO_REF,
    Q_EB_PRODUTO_FINOPS,
    Q_EB_QTD_BROKERS,
    Q_EB_QTD_TOPICOS,
    Q_EB_TOPICO_SCHEMA,
    Q_EB_TRANSFORMACAO,
    Q_FEATURE_NAME,
    Q_MICROSERVICE_NAME,
    Q_OWNER_EMAIL,
    Q_SIGLA,
    Q_SIGLA_APP,
    Q_SQUAD,
    Q_TECH_EMAIL,
    Question,
    pergunta_condicao,
    pergunta_confirmacao,
    pergunta_perfil_compute,
    pergunta_texto_com_sugestao,
)
from .terraform import localizar_infra
from .wizard import (
    STATUS_CANCELADO,
    STATUS_ERRO_AWS,
    STATUS_ESCRITO,
    VALOR_OUTRO,
    com_aws,
    com_escape,
    escolher_ou_digitar,
    perguntar,
)

# Codigo da empresa quando o dev so aperta enter. E o Itau Unibanco: qualquer
# outro numero e excecao, e excecao merece ser digitada.
EMPRESA_PADRAO = "341"

# Organizacao onde os repositorios da area vivem. Entra so como SUGESTAO no
# enunciado do `github_repo_id`.
ORG_GITHUB = "itau-corp"

# Retencao de log sugerida por ambiente. Numeros baixos em dev/hom porque log
# de connector e volumoso e ninguem investiga um incidente de dev de tres
# semanas atras; prod segue o minimo de auditoria da area.
RETENCAO_SUGERIDA = {"dev": 3, "hom": 7, "prod": 30}

# Um item de mapeamento: `$.a.b > $.c` (copia) ou `"CD" > $.origem` (constante).
_ITEM_MAPA = r'(?:\$\.[^\s;>]+|"[^";>]*")\s*>\s*\$\.[^\s;>]+'
_PADRAO_MAPA = rf"{_ITEM_MAPA}(?:\s*;\s*{_ITEM_MAPA})*"

# `nome = valor` ou `nome = valor1; valor2`.
_PADRAO_CAMPO = r"[A-Za-z0-9_.$\[\]-]+\s*=\s*[^;=]+(?:;[^;=]+)*"


class EchoBridgeState(TypedDict, total=False):
    """As chaves que SO o ramo echobridge usa.

    O ramo do worker e este compartilham o comeco do /infra (ambientes,
    conferencia de perfis, `opcoes`/`atual`/`coletados`), entao o estado do
    grafo herda deste TypedDict em vez de ter dois estados separados.
    """

    eb: dict[str, Any]              # respostas que valem para o projeto inteiro
    topicos: list[dict[str, Any]]   # topicos ja fechados
    topico: dict[str, Any]          # topico sendo montado agora
    indice_topico: int
    indice_particao: int            # topico sendo perguntado no ambiente atual
    removidos: list[str]            # sobras do template de worker que foram apagadas


# ---------------------------------------------------------------------------
# Leitura e escrita do estado
# ---------------------------------------------------------------------------

def _guardar(state: dict[str, Any], campo: str, valor: Any) -> dict[str, Any]:
    """Guarda uma resposta no bloco global da aplicacao."""
    return {"eb": {**state.get("eb", {}), campo: valor}}


def _guardar_topico(state: dict[str, Any], campo: str, valor: Any) -> dict[str, Any]:
    return {"topico": {**state.get("topico", {}), campo: valor}}


def _guardar_ambiente(state: dict[str, Any], campo: str, valor: Any) -> dict[str, Any]:
    return {"atual": {**state.get("atual", {}), campo: valor}}


def _ambiente_atual(state: dict[str, Any]) -> str:
    return state["ambientes"][state.get("indice", 0)]


def _de_onde(state: dict[str, Any]) -> str:
    """Perfil, conta e regiao que estao respondendo as listagens.

    Regiao errada nao da erro -- devolve lista vazia. Ver a regiao na tela e o
    que separa "esta conta nao tem cluster nenhum" de "estou olhando para a
    regiao errada".
    """
    opcoes = state.get("opcoes", {})
    return (
        f"Perfil {opcoes.get('perfil', '?')} · conta {opcoes.get('conta', '?')} · "
        f"regiao {opcoes.get('regiao', '?')}"
    )


def _ou_sugestao(resposta: str, sugestao: str) -> str:
    """Enter vazio nos campos com sugestao significa 'aceito a sugestao'."""
    return resposta.strip() or sugestao


# ---------------------------------------------------------------------------
# Parsers das respostas compactas
# ---------------------------------------------------------------------------

def parsear_valores(bruto: str) -> tuple[str, list[str]]:
    """`sigla_sistema = EP9; SF` vira `("sigla_sistema", ["EP9", "SF"])`.

    Um campo e uma lista de valores numa linha so. A alternativa seria duas
    perguntas por criterio de filtro, e o wizard ja tem perguntas demais --
    esta forma cabe numa linha e o `pattern` da pergunta ja recusou o que nao
    encaixa antes de chegar aqui.
    """
    nome, _, resto = bruto.partition("=")
    return nome.strip(), [v.strip() for v in resto.split(";") if v.strip()]


def parsear_lista(bruto: str) -> list[str]:
    """`a; b; c` vira `["a", "b", "c"]`."""
    return [v.strip() for v in bruto.split(";") if v.strip()]


def parsear_mapeamentos(bruto: str) -> list[dict[str, str]]:
    """`$.data.x > $.x ; "CD" > $.origem` vira as regras do mapper.

    Origem entre aspas e uma CONSTANTE (vira `additionalTransform.constant`);
    origem com `$.` e uma copia de campo. Sao as duas unicas formas que o
    modulo aceita, e por isso as duas unicas que o wizard coleta.
    """
    regras: list[dict[str, str]] = []
    for item in bruto.split(";"):
        item = item.strip()
        if not item:
            continue
        origem, _, alvo = item.partition(">")
        origem, alvo = origem.strip(), alvo.strip()
        if origem.startswith('"'):
            regras.append({"constant": origem.strip('"'), "target": alvo})
        else:
            regras.append({"source": origem, "target": alvo})
    return regras


# ---------------------------------------------------------------------------
# Nos: identidade da aplicacao
# ---------------------------------------------------------------------------

def no_comunidade(state: dict[str, Any]) -> dict[str, Any]:
    return _guardar(state, "comunidade", perguntar(Q_EB_COMUNIDADE))


def no_comunidade_texto(state: dict[str, Any]) -> dict[str, Any]:
    """So pergunta se a comunidade escolhida foi 'outra' -- ver regra 3."""
    if state.get("eb", {}).get("comunidade") != VALOR_OUTRO:
        return {}
    return _guardar(state, "comunidade", perguntar(Q_EB_COMUNIDADE_TEXTO))


def _no_simples(campo: str, pergunta: Question):
    """Fabrica um no que faz UMA pergunta e guarda a resposta em `eb`."""

    def no(state: dict[str, Any]) -> dict[str, Any]:
        return _guardar(state, campo, perguntar(pergunta))

    return no


def no_finalidade(state: dict[str, Any]) -> dict[str, Any]:
    return _guardar(state, "finalidade", perguntar(Q_EB_FINALIDADE))


def no_finalidade_texto(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("eb", {}).get("finalidade") != VALOR_OUTRO:
        return {}
    return _guardar(state, "finalidade", perguntar(Q_EB_FINALIDADE_TEXTO))


def no_empresa(state: dict[str, Any]) -> dict[str, Any]:
    resposta = perguntar(Q_EB_EMPRESA)
    return _guardar(state, "empresa", _ou_sugestao(resposta, EMPRESA_PADRAO))


def no_github(state: dict[str, Any]) -> dict[str, Any]:
    """O repositorio, que vira tag e entra no `github_repo_id` do modulo.

    A sugestao sai do nome da pasta do projeto, que nos repositorios da area E
    o nome do repositorio. Vale como sugestao, nunca como certeza: quem clonou
    numa pasta com outro nome so precisa digitar por cima.
    """
    pasta = Path(state["project_root"]).resolve().name
    sugestao = f"{ORG_GITHUB}/{pasta}"
    resposta = perguntar(
        pergunta_texto_com_sugestao(
            "github_repo_id",
            "Qual o repositorio no GitHub (org/nome)?",
            sugestao,
            ajuda="Entra em `github_repo_id`. A parte depois da barra vira `github_repo_name`.",
            pattern=r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+",
            pattern_help="Use o formato organizacao/repositorio. Ex.: itau-corp/itau-fe6-app-echobridge",
        )
    )
    repo_id = _ou_sugestao(resposta, sugestao)
    return {
        "eb": {
            **state.get("eb", {}),
            "github_repo_id": repo_id,
            "github_repo_name": repo_id.split("/")[-1],
        }
    }


def no_secret(state: dict[str, Any]) -> dict[str, Any]:
    """O secret com o certificado do Kafka (kcert.user / kcert.password)."""
    nomes = state.get("opcoes", {}).get("secrets", [])
    pergunta = escolher_ou_digitar(
        "secret_name",
        "Qual o secret com o certificado do Kafka (kcert)?",
        [Option(n, n) for n in nomes],
        ajuda="O data.tf le kcert.user e kcert.password dele. Ex.: KafkaKCert",
        vazio="Nenhum secret foi listado pelo perfil. Informe o nome completo.",
    )
    return _guardar(state, "secret_name", perguntar(pergunta))


def no_modulo_ref(state: dict[str, Any]) -> dict[str, Any]:
    resposta = perguntar(Q_EB_MODULO_REF)
    return _guardar(state, "module_ref", _ou_sugestao(resposta, MODULO_REF_SUGERIDA))


def no_imagem_tag(state: dict[str, Any]) -> dict[str, Any]:
    resposta = perguntar(Q_EB_IMAGEM_TAG)
    return _guardar(state, "image_tag", _ou_sugestao(resposta, IMAGEM_TAG_SUGERIDA))


def no_qtd_topicos(state: dict[str, Any]) -> dict[str, Any]:
    return {
        **_guardar(state, "qtd_topicos", perguntar(Q_EB_QTD_TOPICOS)),
        "indice_topico": 0,
        "topicos": [],
        "topico": {},
    }


# ---------------------------------------------------------------------------
# Nos: o loop por topico
# ---------------------------------------------------------------------------

def _numero_do_topico(state: dict[str, Any]) -> int:
    return state.get("indice_topico", 0) + 1


def no_topico_nome(state: dict[str, Any]) -> dict[str, Any]:
    numero = _numero_do_topico(state)
    total = state.get("eb", {}).get("qtd_topicos", 1)
    pergunta = Question(
        id=f"topico_{numero}",
        kind="text",
        title=f"[topico {numero}/{total}] Qual o nome do topico Kafka?",
        help="O nome completo, como esta no cluster. Ex.: pagamentos-recalculo-debito-automatico-requerido",
        pattern=r"[A-Za-z0-9._-]{1,249}",
        pattern_help="Letras, numeros, ponto, hifen e underscore.",
    )
    return _guardar_topico(state, "nome", perguntar(pergunta))


def no_topico_broker(state: dict[str, Any]) -> dict[str, Any]:
    """Em qual cluster Kafka este topico vive. So pergunta se houver mais de um."""
    quantos = state.get("eb", {}).get("qtd_brokers", 1)
    if quantos <= 1:
        return _guardar_topico(state, "broker", 0)

    numero = _numero_do_topico(state)
    pergunta = Question(
        id=f"topico_broker_{numero}",
        kind="choice",
        title=f"[topico {numero}] Em qual broker este topico vive?",
        help="O endereco de cada broker sera perguntado uma vez por ambiente.",
        options=tuple(Option(str(i), f"Broker {i + 1}") for i in range(quantos)),
    )
    return _guardar_topico(state, "broker", int(perguntar(pergunta)))


def no_topico_schema(state: dict[str, Any]) -> dict[str, Any]:
    return _guardar_topico(state, "schema", perguntar(Q_EB_TOPICO_SCHEMA))


def no_topico_clazz(state: dict[str, Any]) -> dict[str, Any]:
    """A classe do evento. So e obrigatoria quando ha transformacao.

    Ela e o `sourceType` do mapper -- sem ela o modulo nao sabe a qual evento
    aplicar o mapeamento. Quando nao ha transformacao, ainda vale perguntar
    (o filtro por clazz usa o mesmo valor), mas ai o branco e aceito.
    """
    eb = state.get("eb", {})
    if not eb.get("usa_transformacao") and not eb.get("usa_filtro"):
        return _guardar_topico(state, "clazz", "")

    numero = _numero_do_topico(state)
    obrigatoria = bool(eb.get("usa_transformacao"))
    pergunta = Question(
        id=f"topico_clazz_{numero}",
        kind="text",
        title=f"[topico {numero}] Qual a classe (sourceType) do evento?",
        help=(
            "Ex.: br.com.itau.pagamentos.recalculo_debito_automatico_requerido."
            "RecalculoDebitoAutomaticoRequeridoData"
            + ("" if obrigatoria else "\nEnter deixa em branco -- so use se nao for filtrar por classe.")
        ),
        allow_empty=not obrigatoria,
    )
    return _guardar_topico(state, "clazz", perguntar(pergunta))


def no_topico_criterios(state: dict[str, Any]) -> dict[str, Any]:
    """Por qual criterio filtrar ESTE topico. Vazio = publica tudo dele."""
    if not state.get("eb", {}).get("usa_filtro"):
        return _guardar_topico(state, "criterios", [])

    numero = _numero_do_topico(state)
    pergunta = Question(
        id=f"topico_criterios_{numero}",
        kind="multi_choice",
        title=f"[topico {numero}] Por onde filtrar os eventos deste topico?",
        help=(
            "Criterios marcados juntos sao avaliados com AND: o evento tem de\n"
            "atender a todos. Nao marcar nada publica todo evento do topico."
        ),
        allow_empty=True,
        options=(
            Option("header", "Header", "Um cabecalho da mensagem Kafka. Ex.: sigla_sistema"),
            Option("clazz", "Classe", "O tipo do evento (o mesmo sourceType do mapper)."),
            Option("body", "Corpo", "Um campo do payload, em JSONPath. Ex.: $.data.codigo"),
        ),
    )
    return _guardar_topico(state, "criterios", perguntar(pergunta))


def _pulou(state: dict[str, Any], criterio: str) -> bool:
    return criterio not in state.get("topico", {}).get("criterios", [])


def no_filtro_header(state: dict[str, Any]) -> dict[str, Any]:
    if _pulou(state, "header"):
        return {}
    numero = _numero_do_topico(state)
    pergunta = Question(
        id=f"filtro_header_{numero}",
        kind="text",
        title=f"[topico {numero}] Qual header, e com quais valores?",
        help="Formato: nome = valor. Varios valores separados por ';'. Ex.: sigla_sistema = EP9; SF",
        pattern=_PADRAO_CAMPO,
        pattern_help="Use 'nome = valor' (varios valores separados por ';').",
    )
    nome, valores = parsear_valores(perguntar(pergunta))
    return _guardar_topico(state, "_header", {"name": nome, "values": valores})


def no_filtro_header_condicao(state: dict[str, Any]) -> dict[str, Any]:
    if _pulou(state, "header"):
        return {}
    numero = _numero_do_topico(state)
    criterio = dict(state["topico"]["_header"])
    criterio["condition"] = perguntar(
        pergunta_condicao(
            f"filtro_header_cond_{numero}",
            f"[topico {numero}] Como comparar o header '{criterio['name']}'?",
        )
    )
    return _guardar_topico(state, "_header", criterio)


def no_filtro_clazz(state: dict[str, Any]) -> dict[str, Any]:
    if _pulou(state, "clazz"):
        return {}
    numero = _numero_do_topico(state)
    sugestao = state.get("topico", {}).get("clazz", "")
    pergunta = Question(
        id=f"filtro_clazz_{numero}",
        kind="text",
        title=f"[topico {numero}] Quais classes o filtro aceita?",
        help=(
            "Varias separadas por ';'."
            + (f"\nEnter aceita: {sugestao}" if sugestao else "")
        ),
        allow_empty=bool(sugestao),
    )
    bruto = _ou_sugestao(perguntar(pergunta), sugestao)
    return _guardar_topico(state, "_clazz", {"values": parsear_lista(bruto)})


def no_filtro_clazz_condicao(state: dict[str, Any]) -> dict[str, Any]:
    if _pulou(state, "clazz"):
        return {}
    numero = _numero_do_topico(state)
    criterio = dict(state["topico"]["_clazz"])
    criterio["condition"] = perguntar(
        pergunta_condicao(
            f"filtro_clazz_cond_{numero}",
            f"[topico {numero}] Como comparar a classe do evento?",
        )
    )
    return _guardar_topico(state, "_clazz", criterio)


def no_filtro_body(state: dict[str, Any]) -> dict[str, Any]:
    if _pulou(state, "body"):
        return {}
    numero = _numero_do_topico(state)
    pergunta = Question(
        id=f"filtro_body_{numero}",
        kind="text",
        title=f"[topico {numero}] Qual campo do corpo, e com quais valores?",
        help=(
            "Formato: caminho = valor. Varios valores separados por ';'.\n"
            "Ex.: $.data.recebedor.codigo_ispb = 60701190"
        ),
        pattern=_PADRAO_CAMPO,
        pattern_help="Use 'caminho = valor' (varios valores separados por ';').",
    )
    nome, valores = parsear_valores(perguntar(pergunta))
    return _guardar_topico(state, "_body", {"name": nome, "values": valores})


def no_filtro_body_condicao(state: dict[str, Any]) -> dict[str, Any]:
    if _pulou(state, "body"):
        return {}
    numero = _numero_do_topico(state)
    criterio = dict(state["topico"]["_body"])
    criterio["condition"] = perguntar(
        pergunta_condicao(
            f"filtro_body_cond_{numero}",
            f"[topico {numero}] Como comparar o campo '{criterio['name']}'?",
        )
    )
    return _guardar_topico(state, "_body", criterio)


def no_topico_mapeamento(state: dict[str, Any]) -> dict[str, Any]:
    """Como o payload deste topico vira o payload publicado."""
    if not state.get("eb", {}).get("usa_transformacao"):
        return _guardar_topico(state, "mapeamentos", [])

    numero = _numero_do_topico(state)
    pergunta = Question(
        id=f"topico_mapa_{numero}",
        kind="text",
        title=f"[topico {numero}] Qual o mapeamento do payload?",
        help=(
            "Uma regra por item, separadas por ';'. Cada regra e 'origem > destino'.\n"
            "  copiar um campo : $.data.sigla_sistema > $.sigla_sistema\n"
            '  injetar constante: "CD" > $.origem\n'
            "Ex.: \"CD\" > $.origem ; $.data.sigla_sistema > $.sigla_sistema"
        ),
        pattern=_PADRAO_MAPA,
        pattern_help=(
            "Cada regra e 'origem > destino', separadas por ';'. A origem e um "
            'caminho ($.campo) ou uma constante entre aspas ("CD"); o destino e '
            "sempre um caminho ($.campo)."
        ),
    )
    return _guardar_topico(state, "mapeamentos", parsear_mapeamentos(perguntar(pergunta)))


def no_fechar_topico(state: dict[str, Any]) -> dict[str, Any]:
    """Fecha o topico atual e avanca o indice. Sem interrupt e sem escrita."""
    bruto = dict(state.get("topico", {}))

    # Os criterios ficaram em chaves com "_" enquanto eram montados em dois
    # passos (valores e depois condicao). Aqui viram o filtro final.
    filtro = {
        nome: bruto.pop(f"_{nome}")
        for nome in ("header", "clazz", "body")
        if bruto.get(f"_{nome}")
    }
    bruto.pop("criterios", None)
    bruto["filtro"] = filtro

    topicos = [*state.get("topicos", []), bruto]
    return {
        "topicos": topicos,
        "topico": {},
        "indice_topico": state.get("indice_topico", 0) + 1,
    }


def rota_proximo_topico(state: dict[str, Any]) -> str:
    quantos = state.get("eb", {}).get("qtd_topicos", 1)
    return "proximo" if state.get("indice_topico", 0) < quantos else "ambientes"


# ---------------------------------------------------------------------------
# Nos: o loop por ambiente
# ---------------------------------------------------------------------------

def no_conectar_ambiente(state: dict[str, Any]) -> dict[str, Any]:
    """Carrega, de uma vez, tudo o que o ambiente atual precisa listar."""
    ambiente = _ambiente_atual(state)
    ja_conferido = state.get("contas", {}).get(ambiente, {})
    conta = ja_conferido.get("conta", "?")
    regiao = ja_conferido.get("regiao", "?")
    destino = state.get("eb", {}).get("destino", "SNS")

    def tarefa(perfil: str) -> dict[str, Any]:
        if destino == "SNS":
            destinos = aws.listar_topicos_sns(perfil)
        else:
            destinos = aws.arns_de_filas_sqs(perfil, conta, regiao)
        return {
            "opcoes": {
                # Campos de exibicao: ausencia nao pode derrubar o wizard.
                "conta": conta,
                "regiao": regiao,
                "perfil": perfil,
                "clusters": aws.listar_clusters_ecs(perfil),
                "vpcs": aws.listar_vpcs(perfil),
                "destinos": destinos,
                "subnets": [],
                "grupos": [],
            },
            "atual": {},
            # O ciclo das particoes recomeca do primeiro topico a cada ambiente.
            "indice_particao": 0,
        }

    return com_aws(ambiente, tarefa)


def no_cluster(state: dict[str, Any]) -> dict[str, Any]:
    ambiente = _ambiente_atual(state)
    nomes = state.get("opcoes", {}).get("clusters", [])
    pergunta = escolher_ou_digitar(
        "ecs_cluster_name",
        f"[{ambiente}] Em qual cluster ECS o connector vai rodar?",
        [Option(n, n) for n in nomes],
        ajuda=_de_onde(state),
        vazio="Nenhum cluster foi listado nesta conta/regiao. Informe o nome.",
    )
    return _guardar_ambiente(state, "ecs_cluster_name", perguntar(pergunta))


def no_perfil_compute(state: dict[str, Any]) -> dict[str, Any]:
    ambiente = _ambiente_atual(state)
    return _guardar_ambiente(state, "profile", perguntar(pergunta_perfil_compute(ambiente)))


def no_vpc(state: dict[str, Any]) -> dict[str, Any]:
    ambiente = _ambiente_atual(state)
    vpcs = state.get("opcoes", {}).get("vpcs", [])
    pergunta = escolher_ou_digitar(
        "service_vpc_id",
        f"[{ambiente}] Em qual VPC?",
        [Option(v["id"], f"{v['id']}  {v['nome']}", v["cidr"]) for v in vpcs],
        vazio="Nenhuma VPC foi listada. Informe o vpc-id.",
    )
    return _guardar_ambiente(state, "service_vpc_id", perguntar(pergunta))


def no_carregar_rede(state: dict[str, Any]) -> dict[str, Any]:
    """Subnets e security groups da VPC escolhida. Sem interrupt: e chamada de rede."""
    vpc_id = state.get("atual", {}).get("service_vpc_id", "")

    def tarefa(perfil: str) -> dict[str, Any]:
        opcoes = dict(state.get("opcoes", {}))
        opcoes["subnets"] = aws.listar_subnets(perfil, vpc_id)
        opcoes["grupos"] = aws.listar_security_groups(perfil, vpc_id)
        return {"opcoes": opcoes}

    return com_aws(_ambiente_atual(state), tarefa)


def no_subnets(state: dict[str, Any]) -> dict[str, Any]:
    ambiente = _ambiente_atual(state)
    subnets = state.get("opcoes", {}).get("subnets", [])
    if subnets:
        pergunta = Question(
            id="service_subnets",
            kind="multi_choice",
            title=f"[{ambiente}] Em quais subnets o connector vai rodar?",
            help="Escolha uma por zona de disponibilidade, quando possivel.",
            options=tuple(
                Option(s["id"], f"{s['id']}  {s['az']}", f"{s['cidr']}  {s['nome']}")
                for s in subnets
            ),
        )
        return _guardar_ambiente(state, "service_subnets", perguntar(pergunta))

    pergunta = Question(
        id="service_subnets",
        kind="text",
        title=f"[{ambiente}] Quais subnets? (separe por virgula)",
        help="Nenhuma subnet foi listada pelo perfil.",
    )
    bruto = perguntar(pergunta)
    return _guardar_ambiente(
        state, "service_subnets", [p.strip() for p in bruto.split(",") if p.strip()]
    )


def no_cidrs(state: dict[str, Any]) -> dict[str, Any]:
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
        return _guardar_ambiente(state, "service_cidr_blocks", perguntar(pergunta))

    pergunta = Question(
        id="service_cidr_blocks",
        kind="text",
        title=f"[{ambiente}] Quais CIDRs liberar? (separe por virgula)",
        help="Nao consegui derivar os CIDRs das subnets escolhidas.",
    )
    bruto = perguntar(pergunta)
    return _guardar_ambiente(
        state, "service_cidr_blocks", [p.strip() for p in bruto.split(",") if p.strip()]
    )


def no_cidrs_extras(state: dict[str, Any]) -> dict[str, Any]:
    """CIDRs que nao sao de subnet nenhuma.

    O caso real e a faixa dos pods (100.64.0.0/16): o Kafka e o destino vivem
    fora das subnets do servico, e sem essa faixa o connector sobe e nao fala
    com ninguem. Como nao da para derivar de nada, e uma pergunta -- com o
    branco valendo "nao ha nenhum".
    """
    ambiente = _ambiente_atual(state)
    pergunta = Question(
        id="cidr_extras",
        kind="text",
        title=f"[{ambiente}] Precisa liberar mais algum CIDR? (separe por virgula)",
        help="Ex.: 100.64.0.0/16 (faixa dos pods). Enter = nenhum a mais.",
        allow_empty=True,
    )
    extras = [p.strip() for p in perguntar(pergunta).split(",") if p.strip()]
    atuais = state.get("atual", {}).get("service_cidr_blocks", [])
    # `dict.fromkeys` remove repetido preservando a ordem: um CIDR digitado que
    # ja veio da subnet nao pode aparecer duas vezes na lista.
    return _guardar_ambiente(
        state, "service_cidr_blocks", list(dict.fromkeys([*atuais, *extras]))
    )


def no_security_group(state: dict[str, Any]) -> dict[str, Any]:
    ambiente = _ambiente_atual(state)
    grupos = state.get("opcoes", {}).get("grupos", [])
    pergunta = escolher_ou_digitar(
        "security_group",
        f"[{ambiente}] Qual o security group default da VPC?",
        [Option(g["id"], f"{g['id']}  {g['nome']}", g["descricao"]) for g in grupos],
        ajuda="O modulo espera o grupo chamado 'default' -- ele aparece primeiro na lista.",
        vazio="Nenhum security group foi listado. Informe o sg-id.",
    )
    return _guardar_ambiente(state, "security_group", perguntar(pergunta))


def no_kafka_client_id(state: dict[str, Any]) -> dict[str, Any]:
    ambiente = _ambiente_atual(state)
    eb = state.get("eb", {})
    sugestao = f"{eb.get('sigla', '').lower()}-echobridge-consumer-{ambiente}"
    resposta = perguntar(
        pergunta_texto_com_sugestao(
            f"kafka_client_id_{ambiente}",
            f"[{ambiente}] Qual o client_id do consumidor Kafka?",
            sugestao,
            ajuda="E o valor cadastrado na governanca do Kafka para este ambiente.",
        )
    )
    return _guardar_ambiente(state, "kafka_client_id", _ou_sugestao(resposta, sugestao))


def no_kafka_group_id(state: dict[str, Any]) -> dict[str, Any]:
    ambiente = _ambiente_atual(state)
    eb = state.get("eb", {})
    sugestao = (
        f"{eb.get('sigla', '').lower()}-echobridge-itau-"
        f"{eb.get('context', '')}-{ambiente}"
    )
    resposta = perguntar(
        pergunta_texto_com_sugestao(
            f"kafka_group_id_{ambiente}",
            f"[{ambiente}] Qual o group_id do consumidor Kafka?",
            sugestao,
            ajuda=(
                "O group_id define o offset compartilhado. Mudar ele em producao\n"
                "faz o connector reprocessar (ou pular) mensagens."
            ),
        )
    )
    return _guardar_ambiente(state, "kafka_group_id", _ou_sugestao(resposta, sugestao))


def no_bootstrap(state: dict[str, Any]) -> dict[str, Any]:
    """Os enderecos dos brokers NESTE ambiente.

    Kafka nao e recurso da AWS -- nao ha o que listar. Uma pergunta por
    ambiente cobre os N brokers de uma vez, e o `pattern` garante que vieram
    exatamente N: uma lista curta silenciosamente deixaria topicos sem broker.
    """
    ambiente = _ambiente_atual(state)
    quantos = state.get("eb", {}).get("qtd_brokers", 1)
    host = r"[^,\s]+"
    pergunta = Question(
        id=f"bootstrap_{ambiente}",
        kind="text",
        title=(
            f"[{ambiente}] Qual o bootstrap_servers do broker Kafka?"
            if quantos == 1
            else f"[{ambiente}] Quais os bootstrap_servers dos {quantos} brokers, na ordem?"
        ),
        help=(
            "Host e porta. Ex.: kaas-broker-core.dev.aws.cloud.ihf:31101"
            + ("" if quantos == 1 else f"\nSepare os {quantos} por virgula, na ordem Broker 1..{quantos}.")
        ),
        pattern=host + (rf"(?:\s*,\s*{host}){{{quantos - 1}}}" if quantos > 1 else ""),
        pattern_help=(
            f"Informe exatamente {quantos} endereco(s), separados por virgula."
        ),
    )
    bruto = perguntar(pergunta)
    return _guardar_ambiente(
        state, "bootstrap", [p.strip() for p in bruto.split(",") if p.strip()]
    )


def no_particoes(state: dict[str, Any]) -> dict[str, Any]:
    """Quantas particoes CADA topico tem NESTE ambiente.

    E o unico numero do connector que muda de ambiente para ambiente: o mesmo
    topico costuma ter menos particoes em dev do que em producao. Por isso a
    pergunta mora aqui e nao no loop de topicos, e por isso ela nao carrega o
    valor do ambiente anterior como sugestao -- um enter distraido colocaria a
    contagem de dev no tfvars de prod, que e exatamente o erro que esta
    pergunta existe para evitar.

    Este no volta para si mesmo enquanto sobrar topico. E o mesmo padrao dos
    outros ciclos do /infra, so que com uma volta por topico em vez de uma por
    ambiente.
    """
    ambiente = _ambiente_atual(state)
    indice = state.get("indice_particao", 0)
    topico = state["topicos"][indice]
    total = len(state["topicos"])

    pergunta = Question(
        id=f"particoes_{ambiente}_{indice + 1}",
        kind="integer",
        title=(
            f"[{ambiente}] Quantas particoes o topico "
            f"'{topico['nome']}' tem? ({indice + 1}/{total})"
        ),
        help="O modulo usa o numero de particoes para dimensionar o consumo.",
        min_value=1,
        max_value=200,
    )
    valor = perguntar(pergunta)

    # Guardado por NOME do topico, nao por posicao: assim o writer casa cada
    # numero com o seu topico sem depender da ordem em que foram perguntados.
    particoes = {**state.get("atual", {}).get("particoes", {}), topico["nome"]: valor}
    return {
        "atual": {**state.get("atual", {}), "particoes": particoes},
        "indice_particao": indice + 1,
    }


def rota_proxima_particao(state: dict[str, Any]) -> str:
    faltam = state.get("indice_particao", 0) < len(state.get("topicos", []))
    return "proximo" if faltam else "seguir"


def no_destino_arn(state: dict[str, Any]) -> dict[str, Any]:
    ambiente = _ambiente_atual(state)
    destino = state.get("eb", {}).get("destino", "SNS")
    itens = state.get("opcoes", {}).get("destinos", [])
    rotulo = "topico SNS" if destino == "SNS" else "fila SQS"

    opcoes = [Option(i["arn"], i["nome"], i["arn"]) for i in itens]
    pergunta = escolher_ou_digitar(
        "messaging_arn",
        f"[{ambiente}] Em qual {rotulo} o connector publica?",
        com_escape(opcoes) if opcoes else [],
        ajuda=_de_onde(state),
        vazio=f"Nenhum {rotulo} foi listado nesta conta/regiao. Informe o ARN completo.",
    )
    return _guardar_ambiente(state, "messaging_arn", perguntar(pergunta))


def no_destino_arn_texto(state: dict[str, Any]) -> dict[str, Any]:
    """So pergunta se o dev disse que o destino nao esta na lista."""
    if state.get("atual", {}).get("messaging_arn") != VALOR_OUTRO:
        return {}
    ambiente = _ambiente_atual(state)
    destino = state.get("eb", {}).get("destino", "SNS")
    pergunta = Question(
        id=f"messaging_arn_texto_{ambiente}",
        kind="text",
        title=f"[{ambiente}] Qual o ARN completo do destino?",
        help="Ex.: arn:aws:sns:sa-east-1:000000000000:meu_topico",
        pattern=rf"arn:aws:{destino.lower()}:[a-z0-9-]+:[0-9]{{12}}:\S+",
        pattern_help=f"Use um ARN de {destino}. Ex.: arn:aws:{destino.lower()}:sa-east-1:000000000000:recurso",
    )
    return _guardar_ambiente(state, "messaging_arn", perguntar(pergunta))


def no_retencao(state: dict[str, Any]) -> dict[str, Any]:
    ambiente = _ambiente_atual(state)
    sugerido = RETENCAO_SUGERIDA.get(ambiente, 7)
    pergunta = Question(
        id=f"retencao_{ambiente}",
        kind="integer",
        title=f"[{ambiente}] Por quantos dias guardar o log do connector?",
        help=f"O CloudWatch cobra por volume retido. Sugestao para {ambiente}: {sugerido}.",
        min_value=1,
        max_value=3653,
    )
    return _guardar_ambiente(state, "retencao_dias", perguntar(pergunta))


def no_log_level(state: dict[str, Any]) -> dict[str, Any]:
    return _guardar_ambiente(state, "log_level", perguntar(Q_EB_LOG_LEVEL))


def no_fechar_ambiente(state: dict[str, Any]) -> dict[str, Any]:
    """Fecha o ambiente atual e avanca o indice. Sem interrupt e sem escrita."""
    ambiente = _ambiente_atual(state)
    conferido = state.get("contas", {}).get(ambiente, {})
    coletados = [
        *state.get("coletados", []),
        {
            "nome": ambiente,
            "conta": conferido.get("conta", "?"),
            "regiao": conferido.get("regiao", "?"),
            **state.get("atual", {}),
        },
    ]
    return {"coletados": coletados, "indice": state.get("indice", 0) + 1, "atual": {}}


def rota_proximo_ambiente(state: dict[str, Any]) -> str:
    if state.get("status") == STATUS_ERRO_AWS:
        return "parar"
    return "proximo" if state.get("indice", 0) < len(state.get("ambientes", [])) else "revisar"


# ---------------------------------------------------------------------------
# Nos: fim
# ---------------------------------------------------------------------------

def _topicos(state: dict[str, Any]) -> list[Topico]:
    return [
        Topico(
            nome=t["nome"],
            broker=t.get("broker", 0),
            schema=t["schema"],
            clazz=t.get("clazz", ""),
            filtro=t.get("filtro", {}),
            mapeamentos=t.get("mapeamentos", []),
        )
        for t in state.get("topicos", [])
    ]


def _ambientes(state: dict[str, Any]) -> list[AmbienteEcho]:
    return [
        AmbienteEcho(
            nome=a["nome"],
            conta=a["conta"],
            regiao=a["regiao"],
            ecs_cluster_name=a["ecs_cluster_name"],
            profile=a["profile"],
            vpc_id=a["service_vpc_id"],
            subnets=a["service_subnets"],
            cidr_blocks=a["service_cidr_blocks"],
            security_group=a["security_group"],
            kafka_client_id=a["kafka_client_id"],
            kafka_group_id=a["kafka_group_id"],
            bootstrap=a["bootstrap"],
            particoes=a["particoes"],
            messaging_arn=a["messaging_arn"],
            retencao_dias=a["retencao_dias"],
            log_level=a["log_level"],
        )
        for a in state.get("coletados", [])
    ]


def resumo(state: dict[str, Any]) -> str:
    """Texto da revisao: o que vai ser escrito, antes de escrever."""
    eb = state.get("eb", {})
    linhas = [
        f"  Projeto      : {state.get('project_root', '-')}",
        f"  Connector    : {eb.get('feature_name', '?')}-{eb.get('microservice_name', '?')}",
        f"  Repositorio  : {eb.get('github_repo_id', '-')}",
        f"  Modulo       : {eb.get('module_ref', '-')}   imagem {eb.get('image_tag', '-')}",
        f"  Secret kcert : {eb.get('secret_name', '-')}",
        f"  Destino      : {eb.get('destino', '-')}",
        f"  Transformacao: {'sim' if eb.get('usa_transformacao') else 'nao'}"
        f"   ·  Filtro: {'sim' if eb.get('usa_filtro') else 'nao'}",
        "",
        "  Topicos:",
    ]
    for topico in _topicos(state):
        criterios = ", ".join(topico.filtro) or "sem filtro"
        marca = "schema governado" if topico.schema == "governado" else "sem schema"
        linhas.append(
            f"    {topico.nome}  ({marca} · broker {topico.broker + 1} · {criterios}"
            + (f" · {len(topico.mapeamentos)} mapeamentos)" if topico.mapeamentos else ")")
        )
    linhas.append("")

    for ambiente in _ambientes(state):
        linhas += [
            f"  [{ambiente.nome}]  conta {ambiente.conta} · {ambiente.regiao}",
            f"    cluster   : {ambiente.ecs_cluster_name}   perfil {ambiente.profile}",
            f"    vpc       : {ambiente.vpc_id}   sg {ambiente.security_group}",
            f"    subnets   : {', '.join(ambiente.subnets) or '-'}",
            f"    cidrs     : {', '.join(ambiente.cidr_blocks) or '-'}",
            f"    kafka     : {', '.join(ambiente.bootstrap) or '-'}",
            f"                client {ambiente.kafka_client_id} · group {ambiente.kafka_group_id}",
            # As particoes sao por ambiente: sem ve-las lado a lado na revisao
            # ninguem percebe que prod ficou com a contagem de dev.
            "    particoes : "
            + ("  ".join(f"{n}={p}" for n, p in ambiente.particoes.items()) or "-"),
            f"    destino   : {ambiente.messaging_arn}",
            f"    log       : {ambiente.log_level}, {ambiente.retencao_dias} dia(s)",
            "",
        ]
    return "\n".join(linhas)


def no_revisar(state: dict[str, Any]) -> dict[str, Any]:
    """Ultima chance antes de qualquer escrita em disco.

    Ler o disco aqui (para saber o que vai ser APAGADO) e seguro: leitura de
    arquivo e barata e nao muda nada, entao repeti-la a cada retomada do grafo
    nao custa o que custaria repetir uma consulta a AWS. E sem essa lista o dev
    confirmaria uma remocao as cegas.
    """
    texto = resumo(state) + (
        "\n  Os arquivos de infra/terraform e o .iupipes.yml serao SOBRESCRITOS\n"
        "  (ambientes nao escolhidos ficam intactos)."
    )

    try:
        a_remover = sobras(localizar_infra(Path(state["project_root"])))
    except (RuntimeError, OSError):
        # A infra sumiu entre o inicio do wizard e agora. Nao e aqui que isso
        # se resolve: o `escrever` falha com a mensagem certa logo em seguida.
        a_remover = []
    if a_remover:
        texto += "\n\n  E estes arquivos do template de worker serao REMOVIDOS\n"
        texto += "  (o modulo do EchoBridge cria as roles sozinho):\n"
        texto += "\n".join(f"    {c.name}" for c in a_remover)

    if not perguntar(pergunta_confirmacao(texto)):
        return {
            "status": STATUS_CANCELADO,
            "message": "Nada foi escrito. Rode /infra de novo quando quiser.",
        }
    return {}


def rota_confirmacao(state: dict[str, Any]) -> str:
    return "parar" if state.get("status") == STATUS_CANCELADO else "escrever"


def no_escrever(state: dict[str, Any]) -> dict[str, Any]:
    """Unico no que escreve em disco -- e, por isso, unico sem `interrupt()`."""
    raiz = Path(state["project_root"])
    try:
        removidos = remover_sobras(localizar_infra(raiz))
        escritos = escrever_echobridge(
            raiz, state.get("eb", {}), _topicos(state), _ambientes(state)
        )
    except (OSError, PermissionError, KeyError, RuntimeError) as exc:
        return {"status": STATUS_ERRO_AWS, "message": f"falha ao escrever a infra: {exc}"}

    return {
        "status": STATUS_ESCRITO,
        "escritos": [str(c) for c in escritos],
        "removidos": [str(c) for c in removidos],
        "message": (
            "Infra do EchoBridge escrita.\n\n"
            "Proximos passos:\n"
            "  1. revise o diff (o .iupipes.yml foi reescrito por inteiro);\n"
            "  2. confirme a versao do modulo e a tag da imagem nas releases;\n"
            "  3. rode o terraform com o profile do ambiente;\n"
            "  4. o CODEOWNERS nao e gerado -- crie-o com o time dono do repo."
        ),
    }


# ---------------------------------------------------------------------------
# Montagem do ramo
# ---------------------------------------------------------------------------

# A cadeia reta de perguntas da aplicacao. Cada par vira um no; a ordem aqui e
# a ordem em que o dev responde.
_PERGUNTAS_DA_APLICACAO: tuple[tuple[str, Question], ...] = (
    ("sigla", Q_SIGLA),
    ("sigla_app", Q_SIGLA_APP),
    ("context", Q_CONTEXT),
    ("squad", Q_SQUAD),
    ("feature_name", Q_FEATURE_NAME),
    ("microservice_name", Q_MICROSERVICE_NAME),
    ("owner_email", Q_OWNER_EMAIL),
    ("tech_email", Q_TECH_EMAIL),
    ("produto_finops", Q_EB_PRODUTO_FINOPS),
)

# Nos em cadeia reta, na ordem. Cada nome vira `eb_<nome>`, e a aresta e sempre
# do anterior para o proximo -- os nos que so as vezes perguntam se viram
# sozinhos (regra 3 do docstring), entao nao ha rota nenhuma aqui.
_CADEIA_TOPICO = (
    "topico_nome",
    "topico_broker",
    "topico_schema",
    "topico_clazz",
    "topico_criterios",
    "filtro_header",
    "filtro_header_condicao",
    "filtro_clazz",
    "filtro_clazz_condicao",
    "filtro_body",
    "filtro_body_condicao",
    "topico_mapeamento",
)

_CADEIA_AMBIENTE = (
    "cluster",
    "perfil_compute",
    "vpc",
)

_CADEIA_AMBIENTE_POS_REDE = (
    "subnets",
    "cidrs",
    "cidrs_extras",
    "security_group",
    "kafka_client_id",
    "kafka_group_id",
    "bootstrap",
)

# Depois do `bootstrap` entra o ciclo das particoes (uma volta por topico), e
# so entao a cadeia continua.
_CADEIA_AMBIENTE_FINAL = (
    "destino_arn",
    "destino_arn_texto",
    "retencao",
    "log_level",
)

_NOS = {
    "comunidade": no_comunidade,
    "comunidade_texto": no_comunidade_texto,
    "finalidade": no_finalidade,
    "finalidade_texto": no_finalidade_texto,
    "empresa": no_empresa,
    "github": no_github,
    "secret": no_secret,
    "destino": _no_simples("destino", Q_EB_DESTINO),
    "transformacao": _no_simples("usa_transformacao", Q_EB_TRANSFORMACAO),
    "filtro": _no_simples("usa_filtro", Q_EB_FILTRO),
    "modulo_ref": no_modulo_ref,
    "imagem_tag": no_imagem_tag,
    "qtd_brokers": _no_simples("qtd_brokers", Q_EB_QTD_BROKERS),
    "qtd_topicos": no_qtd_topicos,
    "topico_nome": no_topico_nome,
    "topico_broker": no_topico_broker,
    "topico_schema": no_topico_schema,
    "topico_clazz": no_topico_clazz,
    "topico_criterios": no_topico_criterios,
    "filtro_header": no_filtro_header,
    "filtro_header_condicao": no_filtro_header_condicao,
    "filtro_clazz": no_filtro_clazz,
    "filtro_clazz_condicao": no_filtro_clazz_condicao,
    "filtro_body": no_filtro_body,
    "filtro_body_condicao": no_filtro_body_condicao,
    "topico_mapeamento": no_topico_mapeamento,
    "fechar_topico": no_fechar_topico,
    "conectar_ambiente": no_conectar_ambiente,
    "cluster": no_cluster,
    "perfil_compute": no_perfil_compute,
    "vpc": no_vpc,
    "carregar_rede": no_carregar_rede,
    "subnets": no_subnets,
    "cidrs": no_cidrs,
    "cidrs_extras": no_cidrs_extras,
    "security_group": no_security_group,
    "kafka_client_id": no_kafka_client_id,
    "kafka_group_id": no_kafka_group_id,
    "bootstrap": no_bootstrap,
    "particoes": no_particoes,
    "destino_arn": no_destino_arn,
    "destino_arn_texto": no_destino_arn_texto,
    "retencao": no_retencao,
    "log_level": no_log_level,
    "fechar_ambiente": no_fechar_ambiente,
    "revisar": no_revisar,
    "escrever": no_escrever,
}

# A ordem global das perguntas da aplicacao, ate a entrada do loop de topicos.
_CADEIA_GLOBAL = (
    "comunidade",
    "comunidade_texto",
    *[campo for campo, _ in _PERGUNTAS_DA_APLICACAO],
    "finalidade",
    "finalidade_texto",
    "empresa",
    "github",
    "secret",
    "destino",
    "transformacao",
    "filtro",
    "modulo_ref",
    "imagem_tag",
    "qtd_brokers",
    "qtd_topicos",
)


def _nome(chave: str) -> str:
    """Prefixo `eb_` em todo no: o grafo do /infra tem os dois ramos juntos."""
    return f"eb_{chave}"


def _encadear(grafo, chaves: tuple[str, ...]) -> None:
    for atual, proximo in zip(chaves, chaves[1:]):
        grafo.add_edge(_nome(atual), _nome(proximo))


def registrar(grafo, rota_aws) -> str:
    """Acrescenta o ramo echobridge ao grafo do /infra.

    Devolve o nome do primeiro no, para o /infra ligar a saida do
    `confirmar_perfis` nele. `rota_aws` vem de fora para os dois ramos usarem
    exatamente a mesma regra de "a AWS falhou, encerre".
    """
    for chave, funcao in _NOS.items():
        grafo.add_node(_nome(chave), funcao)
    for campo, pergunta in _PERGUNTAS_DA_APLICACAO:
        grafo.add_node(_nome(campo), _no_simples(campo, pergunta))

    _encadear(grafo, _CADEIA_GLOBAL)
    grafo.add_edge(_nome(_CADEIA_GLOBAL[-1]), _nome(_CADEIA_TOPICO[0]))

    _encadear(grafo, _CADEIA_TOPICO)
    grafo.add_edge(_nome(_CADEIA_TOPICO[-1]), _nome("fechar_topico"))
    grafo.add_conditional_edges(
        _nome("fechar_topico"),
        rota_proximo_topico,
        {
            "proximo": _nome(_CADEIA_TOPICO[0]),
            "ambientes": _nome("conectar_ambiente"),
        },
    )

    # A consulta a AWS e o unico ponto do loop que pode encerrar o fluxo.
    grafo.add_conditional_edges(
        _nome("conectar_ambiente"),
        rota_aws,
        {"continuar": _nome(_CADEIA_AMBIENTE[0]), "parar": END},
    )
    _encadear(grafo, _CADEIA_AMBIENTE)
    grafo.add_edge(_nome(_CADEIA_AMBIENTE[-1]), _nome("carregar_rede"))
    grafo.add_conditional_edges(
        _nome("carregar_rede"),
        rota_aws,
        {"continuar": _nome(_CADEIA_AMBIENTE_POS_REDE[0]), "parar": END},
    )
    _encadear(grafo, _CADEIA_AMBIENTE_POS_REDE)

    # O ciclo das particoes: um no que volta para si mesmo enquanto sobrar
    # topico. Cada volta pergunta as particoes de UM topico neste ambiente.
    grafo.add_edge(_nome(_CADEIA_AMBIENTE_POS_REDE[-1]), _nome("particoes"))
    grafo.add_conditional_edges(
        _nome("particoes"),
        rota_proxima_particao,
        {"proximo": _nome("particoes"), "seguir": _nome(_CADEIA_AMBIENTE_FINAL[0])},
    )

    _encadear(grafo, _CADEIA_AMBIENTE_FINAL)
    grafo.add_edge(_nome(_CADEIA_AMBIENTE_FINAL[-1]), _nome("fechar_ambiente"))

    grafo.add_conditional_edges(
        _nome("fechar_ambiente"),
        rota_proximo_ambiente,
        {
            "proximo": _nome("conectar_ambiente"),
            "revisar": _nome("revisar"),
            "parar": END,
        },
    )

    grafo.add_conditional_edges(
        _nome("revisar"),
        rota_confirmacao,
        {"escrever": _nome("escrever"), "parar": END},
    )
    grafo.add_edge(_nome("escrever"), END)

    return _nome(_CADEIA_GLOBAL[0])
