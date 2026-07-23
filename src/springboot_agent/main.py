"""Ponto de entrada (CLI).

Uso:
    python -m springboot_agent.main [--yes] <caminho-do-projeto> [instrucao]

Opcoes:
    --yes, -y   Pula as confirmacoes (auto-aprova escritas e Maven). Use para
                automacao. Sem a flag, o agente pede aprovacao (s/N) antes de
                sobrescrever arquivos ou rodar Maven.

Exemplo:
    python -m springboot_agent.main C:\\dev\\meu-projeto ^
        "Configure para uma API REST com JPA e PostgreSQL"
"""

from __future__ import annotations

import sys

from langchain_core.messages import HumanMessage

from .config import set_auto_approve, set_project_root
from .graph import build_graph

INSTRUCAO_PADRAO = (
    "Analise este projeto Spring Boot novo e configure-o com boas praticas: "
    "ajuste o pom.xml com as dependencias corretas, organize os pacotes por "
    "camada e crie as configuracoes de infraestrutura basicas. Ao final, "
    "rode o Maven para validar."
)


def _formatar_evento(evento: dict) -> None:
    """Imprime de forma legivel cada passo do agente (streaming)."""
    for _no, valor in evento.items():
        for mensagem in valor.get("messages", []):
            # Mensagem do modelo com pedidos de ferramenta
            tool_calls = getattr(mensagem, "tool_calls", None)
            if tool_calls:
                for tc in tool_calls:
                    print(f"  [ferramenta] {tc['name']}({tc['args']})")
            # Texto do modelo
            conteudo = getattr(mensagem, "content", "")
            if isinstance(conteudo, str) and conteudo.strip():
                print(f"\n[Claude]\n{conteudo}\n")
            # Resultado de ferramenta (ToolMessage)
            elif getattr(mensagem, "type", "") == "tool":
                texto = str(mensagem.content)
                resumo = texto if len(texto) < 500 else texto[:500] + " ...[+]"
                print(f"  -> {resumo}")


def main() -> int:
    # Separa as flags dos argumentos posicionais.
    args = sys.argv[1:]
    auto_aprovar = False
    posicionais: list[str] = []
    for arg in args:
        if arg in ("--yes", "-y"):
            auto_aprovar = True
        else:
            posicionais.append(arg)

    if not posicionais:
        print(__doc__)
        return 1

    set_auto_approve(auto_aprovar)
    caminho_projeto = posicionais[0]
    instrucao = posicionais[1] if len(posicionais) > 1 else INSTRUCAO_PADRAO

    try:
        raiz = set_project_root(caminho_projeto)
    except (NotADirectoryError, FileNotFoundError) as exc:
        print(f"ERRO: {exc}")
        return 1

    modo = "AUTO-APROVACAO (--yes)" if auto_aprovar else "confirmacao antes de editar"
    print(f"Projeto alvo: {raiz}")
    print(f"Modo: {modo}")
    print(f"Instrucao: {instrucao}\n" + "=" * 60)

    grafo = build_graph()
    estado_inicial = {"messages": [HumanMessage(content=instrucao)]}

    # recursion_limit: teto de passos para evitar loops infinitos.
    config = {"recursion_limit": 100}

    for evento in grafo.stream(estado_inicial, config=config, stream_mode="updates"):
        _formatar_evento(evento)

    print("=" * 60 + "\nConcluido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
