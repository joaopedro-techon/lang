"""Os grafos do agente, desenhados a partir deles mesmos.

Um diagrama escrito a mao envelhece em silencio: alguem mexe numa aresta, o
desenho continua igual, e o erro so aparece quando alguem apresenta. Aqui o
desenho SAI do grafo compilado -- se o codigo mudar e o `.mmd` nao for
regerado, o diff do proximo `/grafo` denuncia.

Quem faz o trabalho e o proprio LangGraph: `grafo.get_graph()` devolve a
representacao desenhavel (um `Graph` do langchain-core) e `.draw_mermaid()` a
transforma em texto Mermaid. Nao ha dependencia nova nisso, e nao ha rede: o
Mermaid e gerado localmente, ao contrario do `draw_mermaid_png()`, que manda a
estrutura do grafo para a API publica do mermaid.ink.

Nao ha LLM neste arquivo. Desenhar o grafo da conversa NAO chama modelo nenhum
-- e por isso o `/grafo` funciona numa maquina sem credencial, como os outros
comandos deterministicos.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import resolve_inside_project
from .graph import build_graph
from .infra import build_infra_graph
from .initialize import build_initialize_graph

# Onde os .mmd sao gravados, relativo a raiz do projeto.
#
# Dentro do `.custodia/`, e nao em `docs/`, por um motivo pratico: a CLI roda no
# repositorio do CLIENTE. A pasta `docs/` e dele -- despejar ali diagramas das
# entranhas do agente e invadir a documentacao de quem so queria usar a
# ferramenta. O `.custodia/` ja e o espaco do agente no projeto alvo (e onde
# mora a spec.json), entao e ali que o que e nosso fica.
SUBPASTA_PADRAO = ".custodia/grafos"


class _SemModelo:
    """Ocupa o lugar do chat model enquanto o grafo e apenas desenhado.

    O no `assistant` guarda esta referencia mas so a usa dentro do `invoke`, e
    desenhar nunca invoca. Se alguem um dia tentar CONVERSAR com um grafo
    montado assim, o erro precisa dizer o que aconteceu -- dai o `__getattr__`
    abaixo, em vez de deixar estourar um `AttributeError` sem contexto.
    """

    def __getattr__(self, nome: str) -> Any:
        raise RuntimeError(
            "este grafo foi montado apenas para ser desenhado (sem modelo). "
            "Use build_graph() sem argumentos para conversar."
        )


@dataclass(frozen=True)
class Grafo:
    """Um grafo que o agente sabe desenhar."""

    slug: str
    rotulo: str
    # Como o comando classifica o fluxo na tela: com LLM ou deterministico.
    usa_llm: bool
    construtor: Callable[[], Any]
    # Uma linha explicando o que o desenho mostra.
    nota: str


# O registro e a FONTE UNICA. Um grafo novo (o /generate, quando existir) e uma
# entrada aqui -- o comando, os arquivos gravados e a listagem acompanham
# sozinhos.
GRAFOS: tuple[Grafo, ...] = (
    Grafo(
        slug="conversa",
        rotulo="Conversa (/chat e texto solto)",
        usa_llm=True,
        construtor=lambda: build_graph(llm_com_tools=_SemModelo()),
        nota="Loop ReAct: o modelo decide se precisa de ferramenta e volta.",
    ),
    Grafo(
        slug="initialize",
        rotulo="/initialize",
        usa_llm=False,
        construtor=build_initialize_graph,
        nota="Coleta da spec. Nenhum no chama modelo; so o ultimo escreve em disco.",
    ),
    Grafo(
        slug="infra",
        rotulo="/infra",
        usa_llm=False,
        construtor=build_infra_graph,
        nota="Terraform por ambiente. O ciclo repete as perguntas para dev, hom e prod.",
    ),
)


def grafo(slug: str) -> Grafo:
    """Acha um grafo pelo slug, ou explica quais existem."""
    for item in GRAFOS:
        if item.slug == slug:
            return item
    disponiveis = ", ".join(g.slug for g in GRAFOS)
    raise KeyError(f"grafo '{slug}' nao existe. Disponiveis: {disponiveis}.")


def mermaid(slug: str) -> str:
    """O diagrama de um grafo, em texto Mermaid."""
    return grafo(slug).construtor().get_graph().draw_mermaid()


def destino(slug: str, subpasta: str = SUBPASTA_PADRAO) -> Path:
    """Onde o .mmd de um grafo vai ser gravado.

    A raiz nao e parametro de proposito: quem manda e o `project_root` do
    processo, o mesmo que as ferramentas do agente respeitam. E passa pela mesma
    barreira que protege toda escrita: um `subpasta` apontando para fora do
    projeto e recusado por `resolve_inside_project`, nao aceito em silencio.
    """
    return resolve_inside_project(f"{subpasta}/{slug}.mmd")


def exportar(subpasta: str = SUBPASTA_PADRAO) -> list[Path]:
    """Grava um .mmd por grafo e devolve os caminhos, na ordem do registro."""
    escritos: list[Path] = []
    for item in GRAFOS:
        caminho = destino(item.slug, subpasta)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n" para o arquivo nao mudar de conteudo so por ter sido
        # gerado no Windows -- senao todo /grafo aqui vira diff de CRLF.
        caminho.write_text(
            mermaid(item.slug).rstrip("\n") + "\n", encoding="utf-8", newline="\n"
        )
        escritos.append(caminho)
    return escritos
