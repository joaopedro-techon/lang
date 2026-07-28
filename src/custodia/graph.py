"""O orquestrador: o grafo do LangGraph.

Este e o coracao do agente. Montamos um loop ReAct classico (o padrao de
"agente que usa ferramentas") de forma EXPLICITA, para voce enxergar a
orquestracao em vez de usar uma caixa-preta:

    START -> assistant -> (tem tool_call?) --sim--> tools -> assistant
                              |
                             nao
                              v
                             END

- "assistant": chama o Claude com as ferramentas disponiveis.
- "tools": executa as ferramentas que o Claude pediu e devolve os resultados.
- A aresta condicional decide se continua chamando ferramentas ou termina.
"""

from __future__ import annotations

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

from .config import MODEL_NAME
from .prompts import SYSTEM_PROMPT
from .tools import ALL_TOOLS


def build_graph():
    """Constroi e compila o grafo do agente."""

    # O modelo, com as ferramentas "amarradas" a ele. Assim o Claude sabe
    # quais ferramentas existem e pode pedir para chama-las.
    llm = ChatAnthropic(model=MODEL_NAME, max_tokens=16_000)
    llm_com_tools = llm.bind_tools(ALL_TOOLS)

    def assistant(state: MessagesState) -> dict:
        """No do modelo: injeta o system prompt e chama o Claude."""
        mensagens = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        resposta = llm_com_tools.invoke(mensagens)
        return {"messages": [resposta]}

    # MessagesState ja traz um campo "messages" que acumula o historico.
    grafo = StateGraph(MessagesState)

    grafo.add_node("assistant", assistant)
    grafo.add_node("tools", ToolNode(ALL_TOOLS))

    grafo.add_edge(START, "assistant")
    # tools_condition: se a ultima mensagem do assistant tiver tool_calls,
    # vai para "tools"; senao, vai para END.
    grafo.add_conditional_edges("assistant", tools_condition)
    grafo.add_edge("tools", "assistant")

    return grafo.compile()
