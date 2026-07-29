"""O comando /initialize: um grafo LangGraph 100% deterministico.

Nao ha LLM nenhum neste arquivo. E de proposito.

Por que um grafo, se nao tem IA?
--------------------------------
Poderiamos ter escrito isto como uma sequencia de `input()`. Usar o LangGraph
aqui traz coisas que a sequencia de `input()` nao tem:

- O fluxo vira um DIAGRAMA explicito (nos + arestas). As regras de negocio
  ("app encerra com aviso", "schedule encerra com aviso") sao arestas
  condicionais que da para ler e auditar, nao ifs perdidos no meio do codigo.
- `interrupt()` + checkpointer separam a PERGUNTA de QUEM PERGUNTA. O grafo
  emite um JSON descrevendo a pergunta e congela; o terminal responde hoje,
  uma UI web poderia responder amanha, sem tocar no grafo.
- O mesmo motor (LangGraph) roda os comandos deterministicos e os comandos
  com LLM que virao depois, entao existe uma unica forma de orquestrar.

O fluxo
-------

    START
      |
      v
    tipo do projeto? ---- "app" -----------> END  (feature indisponivel)
      | "worker"
      v
    gatilho? ------------ "schedule" ------> END  (feature indisponivel)
      | "sqs"
      v
    nome da fila
      |
      v
    mensagens por segundo
      |
      v
    dependencias
      |
      v
    revisar/confirmar --- "nao" -----------> END  (cancelado)
      | "sim"
      v
    salvar spec.json --------------------> END

Pegadinha importante do interrupt
---------------------------------
Quando o grafo e retomado, o no que pausou RODA DE NOVO desde a primeira
linha -- `interrupt()` nao retoma "no meio" da funcao. Por isso todo no aqui
segue duas regras: (1) um unico `interrupt()` por no, e (2) nenhum efeito
colateral (escrever arquivo, imprimir) antes dele. Repare que o unico no que
escreve em disco -- `salvar` -- nao tem interrupt nenhum.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .questions import (
    Q_DEPENDENCIAS,
    Q_FILA_SQS,
    Q_GATILHO,
    Q_THROUGHPUT,
    Q_TIPO_PROJETO,
    Question,
    pergunta_confirmacao,
    validate,
)
from .spec import ProjectSpec, SqsConfig, save_spec, spec_exists

# Valores possiveis de state["status"] ao final do grafo.
STATUS_BLOQUEADO = "blocked"     # escolheu uma feature que ainda nao existe
STATUS_CANCELADO = "cancelled"   # nao confirmou na revisao
STATUS_SALVO = "saved"           # spec.json gravada


class InitializeState(TypedDict, total=False):
    """O estado que atravessa o grafo.

    `total=False` significa que todas as chaves sao opcionais: o estado comeca
    praticamente vazio e cada no acrescenta o seu pedaco. Cada no devolve um
    dict PARCIAL, e o LangGraph faz o merge no estado acumulado.
    """

    project_root: str          # entrada: raiz do projeto alvo
    agent_version: str         # entrada: gravado na spec como "generated_by"

    project_type: str
    trigger: str
    queue_name: str
    messages_per_second: int
    dependencies: list[str]

    status: str                # um dos STATUS_* acima
    message: str               # mensagem final para o usuario
    spec_path: str             # onde a spec foi gravada (se foi)


# ---------------------------------------------------------------------------
# Auxiliares compartilhados pelos nos
# ---------------------------------------------------------------------------

def _perguntar(pergunta: Question) -> Any:
    """Pausa o grafo, entrega a pergunta ao frontend e valida o que voltou.

    `interrupt(payload)` congela a execucao e devolve o payload para quem
    chamou `invoke()`. Quando o frontend retoma com `Command(resume=valor)`,
    esta mesma chamada passa a devolver `valor`.

    A validacao aqui e uma REDE DE SEGURANCA. O terminal ja valida antes de
    responder (para reperguntar na hora, com mensagem amigavel). Este segundo
    check garante que o invariante vale mesmo que o frontend tenha bug ou seja
    outro no futuro -- se vier lixo, o comando falha alto em vez de gravar uma
    spec invalida.
    """
    resposta = interrupt(pergunta.to_dict())
    return validate(pergunta, resposta)


def _registrar_escolha(pergunta: Question, valor: str, campo: str) -> dict[str, Any]:
    """Guarda a escolha no estado e sinaliza se a feature ainda nao existe.

    Opcoes marcadas com `available=False` no catalogo (hoje: "App" e
    "Schedule") sao selecionaveis, mas encerram o fluxo com a nota explicando
    que a feature ainda nao esta disponivel. Como a regra mora no catalogo, dar
    suporte a uma delas no futuro e so virar o flag para True.
    """
    opcao = pergunta.option(valor)
    if opcao is not None and not opcao.available:
        return {campo: valor, "status": STATUS_BLOQUEADO, "message": opcao.note}
    return {campo: valor}


def _rota_disponibilidade(state: InitializeState) -> str:
    """Aresta condicional: seguir o fluxo ou parar por feature indisponivel."""
    return "parar" if state.get("status") == STATUS_BLOQUEADO else "continuar"


def resumo_da_configuracao(state: InitializeState) -> str:
    """Texto do resumo mostrado na revisao e no fim do comando."""
    labels_dependencias = []
    for valor in state.get("dependencies", []):
        opcao = Q_DEPENDENCIAS.option(valor)
        labels_dependencias.append(opcao.label if opcao else valor)

    linhas = [
        f"  Tipo de projeto      : {_label(Q_TIPO_PROJETO, state.get('project_type'))}",
        f"  Gatilho              : {_label(Q_GATILHO, state.get('trigger'))}",
        f"  Fila SQS             : {state.get('queue_name', '-')}",
        f"  Mensagens por segundo: {state.get('messages_per_second', '-')}",
        f"  Dependencias         : {', '.join(labels_dependencias) or 'nenhuma'}",
    ]
    return "\n".join(linhas)


def _label(pergunta: Question, valor: Any) -> str:
    """Converte o valor tecnico ('sqs') no rotulo legivel ('Consumo SQS')."""
    if not isinstance(valor, str):
        return "-"
    opcao = pergunta.option(valor)
    return opcao.label if opcao else valor


# ---------------------------------------------------------------------------
# Os nos
# ---------------------------------------------------------------------------

def no_tipo_projeto(state: InitializeState) -> dict[str, Any]:
    """Passo 1: Worker ou App?"""
    escolha = _perguntar(Q_TIPO_PROJETO)
    return _registrar_escolha(Q_TIPO_PROJETO, escolha, campo="project_type")


def no_gatilho(state: InitializeState) -> dict[str, Any]:
    """Passo 2: consumo SQS ou schedule?"""
    escolha = _perguntar(Q_GATILHO)
    return _registrar_escolha(Q_GATILHO, escolha, campo="trigger")


def no_fila(state: InitializeState) -> dict[str, Any]:
    """Passo 3: nome da fila SQS."""
    return {"queue_name": _perguntar(Q_FILA_SQS)}


def no_throughput(state: InitializeState) -> dict[str, Any]:
    """Passo 4: vazao esperada, em mensagens por segundo."""
    return {"messages_per_second": _perguntar(Q_THROUGHPUT)}


def no_dependencias(state: InitializeState) -> dict[str, Any]:
    """Passo 5: dependencias do projeto (pode ser nenhuma)."""
    return {"dependencies": _perguntar(Q_DEPENDENCIAS)}


def no_revisar(state: InitializeState) -> dict[str, Any]:
    """Passo 6: mostra tudo junto e pede a confirmacao final.

    Ultima chance de desistir antes de qualquer escrita em disco.
    """
    raiz = Path(state["project_root"])
    # Mostrar a raiz aqui e a ultima defesa contra rodar o wizard na pasta
    # errada -- e o unico momento em que o dev ve o destino antes da escrita.
    resumo = f"  Projeto              : {raiz}\n" + resumo_da_configuracao(state)
    if spec_exists(raiz):
        resumo += "\n\n  ATENCAO: ja existe uma spec neste projeto e ela sera sobrescrita."

    if not _perguntar(pergunta_confirmacao(resumo)):
        return {
            "status": STATUS_CANCELADO,
            "message": "Nada foi salvo. Rode /initialize de novo quando quiser.",
        }
    return {}


def _rota_confirmacao(state: InitializeState) -> str:
    return "parar" if state.get("status") == STATUS_CANCELADO else "salvar"


def no_salvar(state: InitializeState) -> dict[str, Any]:
    """Passo 7: grava o .custodia/spec.json.

    Unico no que escreve em disco -- e, por isso, unico no sem `interrupt()`
    (lembre que um no com interrupt roda de novo inteiro ao ser retomado).
    """
    spec = ProjectSpec(
        project_type=state["project_type"],
        trigger=state["trigger"],
        dependencies=state.get("dependencies", []),
        sqs=SqsConfig(
            queue_name=state["queue_name"],
            messages_per_second=state["messages_per_second"],
        ),
    )
    caminho = save_spec(
        Path(state["project_root"]),
        spec,
        agent_version=state.get("agent_version", "Custod.IA"),
    )
    return {
        "status": STATUS_SALVO,
        "spec_path": str(caminho),
        "message": "Configuracao salva.",
    }


# ---------------------------------------------------------------------------
# Montagem do grafo
# ---------------------------------------------------------------------------

def build_initialize_graph():
    """Monta e compila o grafo do /initialize.

    O checkpointer (MemorySaver) e OBRIGATORIO para usar `interrupt()`: e ele
    que guarda o estado enquanto o grafo esta pausado esperando a resposta.
    Guardamos em memoria porque o wizard dura uma sessao; trocar por
    SqliteSaver bastaria para o usuario poder retomar um /initialize no dia
    seguinte.
    """
    grafo = StateGraph(InitializeState)

    grafo.add_node("tipo_projeto", no_tipo_projeto)
    grafo.add_node("gatilho", no_gatilho)
    grafo.add_node("fila", no_fila)
    grafo.add_node("throughput", no_throughput)
    grafo.add_node("dependencias", no_dependencias)
    grafo.add_node("revisar", no_revisar)
    grafo.add_node("salvar", no_salvar)

    grafo.add_edge(START, "tipo_projeto")

    # "App" ainda nao existe -> encerra depois do passo 1.
    grafo.add_conditional_edges(
        "tipo_projeto",
        _rota_disponibilidade,
        {"continuar": "gatilho", "parar": END},
    )

    # "Schedule" ainda nao existe -> encerra depois do passo 2.
    grafo.add_conditional_edges(
        "gatilho",
        _rota_disponibilidade,
        {"continuar": "fila", "parar": END},
    )

    # Daqui para baixo o caminho e unico: worker + SQS.
    grafo.add_edge("fila", "throughput")
    grafo.add_edge("throughput", "dependencias")
    grafo.add_edge("dependencias", "revisar")

    grafo.add_conditional_edges(
        "revisar",
        _rota_confirmacao,
        {"salvar": "salvar", "parar": END},
    )
    grafo.add_edge("salvar", END)

    return grafo.compile(checkpointer=MemorySaver())
