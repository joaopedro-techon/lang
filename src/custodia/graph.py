"""O orquestrador: o grafo do LangGraph.

Este e o coracao do agente. Montamos um loop ReAct classico (o padrao de
"agente que usa ferramentas") de forma EXPLICITA, para voce enxergar a
orquestracao em vez de usar uma caixa-preta:

    START -> assistant -> (tem tool_call?) --sim--> tools -> assistant
                              |
                             nao
                              v
                             END

- "assistant": chama o modelo com as ferramentas disponiveis.
- "tools": executa as ferramentas que o modelo pediu e devolve os resultados.
- A aresta condicional decide se continua chamando ferramentas ou termina.

Nada aqui sabe QUAL modelo esta respondendo: `build_llm()` (em `llm.py`) le o
provedor do .env e devolve um chat model do LangChain, e o loop abaixo funciona
igual com Claude, GPT, Gemini ou um modelo local.
"""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

from .llm import build_llm_com_tools
from .prompts import SYSTEM_PROMPT
from .tools import ALL_TOOLS


def build_graph():
    """Constroi e compila o grafo do agente."""

    # O modelo, com as ferramentas "amarradas" a ele (assim ele sabe quais
    # existem e pode pedir para chama-las) e com o cache de prompt ligado.
    llm_com_tools = build_llm_com_tools(ALL_TOOLS)

    def assistant(state: MessagesState) -> dict:
        """No do modelo: injeta o system prompt e chama o LLM."""
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
