"""A base de conhecimento (RAG): de onde vem a arquitetura de referencia.

Duvida sobre o CODIGO o agente resolve lendo o repositorio (`read_file`).
Duvida sobre a ARQUITETURA DE REFERENCIA da area -- padroes, convencoes,
decisoes ja tomadas -- o repositorio nao responde: isso mora na base de
conhecimento vetorial da empresa.

O RAG tem tres etapas, e aqui fazemos so a do meio:

    indexacao (solucao interna)  ->  BUSCA (este arquivo)  ->  geracao (o LLM)

Nao indexamos, nao quebramos documento em pedacos, nao geramos embedding: a
base ja existe pronta. Nosso trabalho e consultar e devolver os trechos num
formato que caiba no contexto do modelo.

Este e o unico arquivo que fala com a API de BUSCA do SDK interno
(`iaragenai`). Isso e proposital: quando a API interna mudar, muda so aqui -- a
ferramenta em `tools.py`, o grafo e o prompt continuam iguais. Quem constroi o
cliente e o `iara.py`, compartilhado com o `llm.py`.

>>> AJUSTE NA EMPRESA <<<
O que nao dava para confirmar fora da rede interna esta marcado com `AJUSTAR`
no corpo do arquivo: a assinatura exata da chamada de busca (`_buscar`). O resto
do arquivo nao depende do formato da resposta -- ver `_normalizar`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import KB_ID, KB_TOP_K, KB_VERSION_ID
from .iara import IaraIndisponivel
from .iara import cliente as cliente_iara


class KBIndisponivel(RuntimeError):
    """A base nao pode ser consultada (nao configurada, SDK ausente, rede)."""


@dataclass(frozen=True)
class Trecho:
    """Um pedaco de documento recuperado, com de onde ele veio.

    A `origem` nao e enfeite: sem ela o agente responde sem fonte, e resposta
    sem fonte em custodia de ativos nao serve para auditar nada.
    """

    texto: str
    origem: str
    score: float | None = None


def esta_configurada() -> bool:
    """Da para consultar? Sem KB_ID a ferramenta se declara indisponivel."""
    return bool(KB_ID)


# ---------------------------------------------------------------------------
# A ponte com o SDK interno
# ---------------------------------------------------------------------------

def _cliente() -> Any:
    """O cliente do SDK interno -- o MESMO que o modelo usa.

    A construcao (credencial, ambiente, cache do processo) mora em `iara.py`,
    porque o `llm.py` precisa exatamente do mesmo cliente. Aqui so traduzimos o
    erro para o vocabulario da KB: quem chama esta funcao trata `KBIndisponivel`
    e continua a conversa sem a base, enquanto um `IaraIndisponivel` cru
    derrubaria o turno.
    """
    try:
        return cliente_iara()
    except IaraIndisponivel as exc:
        raise KBIndisponivel(str(exc)) from exc


def _buscar(cliente: Any, texto_consulta: str, top_k: int) -> Any:
    """A chamada de busca por similaridade propriamente dita.

    >>> AJUSTAR NA EMPRESA <<<
    O print que voce mandou mostra a montagem da `kb_reference` e para logo
    antes desta chamada, entao a assinatura abaixo e a leitura mais provavel
    dos nomes do SDK -- nao uma copia do codigo de voces. Confira contra o
    `consultar_kb.py` original e ajuste os nomes dos parametros se preciso.

    O que importa e o CONTRATO desta funcao, nao o corpo dela: recebe consulta
    e top_k, devolve a resposta crua do SDK. Quem entende a resposta e o
    `_normalizar`, logo abaixo -- entao mexer aqui nao quebra o resto.
    """
    from iaragenai.apis.resources.datafoundation_api.types import (  # type: ignore[import-not-found]
        SimilaritySearchKnowledgeBaseVersionReference,
        SimilaritySearchStrategyType,
    )

    referencia = SimilaritySearchKnowledgeBaseVersionReference(
        knowledge_base_id=KB_ID,
        knowledge_base_version_id=KB_VERSION_ID if KB_VERSION_ID else None,
    )

    return cliente.datafoundation.similarity_search(
        knowledge_base=referencia,
        query=texto_consulta,
        top_k=top_k,
        strategy_type=SimilaritySearchStrategyType.SIMILARITY,
    )


def consultar(texto_consulta: str, limite: int | None = None) -> list[Trecho]:
    """Busca na base e devolve os trechos mais parecidos com a consulta.

    Levanta `KBIndisponivel` em qualquer falha -- quem chama (a ferramenta)
    transforma isso numa mensagem que o modelo consegue ler e contornar.
    """
    if not esta_configurada():
        raise KBIndisponivel("KB_ID nao configurado no .env -- base nao consultada.")

    top_k = limite if limite and limite > 0 else KB_TOP_K
    cliente = _cliente()

    try:
        resposta = _buscar(cliente, texto_consulta, top_k)
    except ImportError as exc:
        raise KBIndisponivel(f"SDK interno incompleto: {exc}") from exc
    except Exception as exc:
        raise KBIndisponivel(f"falha ao consultar a base: {exc}") from exc

    return _normalizar(resposta, top_k)


# ---------------------------------------------------------------------------
# Leitura da resposta
# ---------------------------------------------------------------------------

# O formato exato da resposta so da para confirmar rodando dentro da empresa.
# Em vez de apostar num nome de campo e quebrar em producao, aceitamos os
# nomes usuais de SDK de busca vetorial e ficamos com o primeiro que existir.
# E defensivo de proposito: o custo de errar aqui e o agente responder "nao
# encontrei nada" com a base cheia -- uma falha silenciosa e cara de achar.
_CAMPOS_LISTA = ("resultados", "results", "documents", "matches", "data", "items")
_CAMPOS_TEXTO = ("texto", "content", "text", "chunk", "page_content", "conteudo")
_CAMPOS_METADADOS = ("metadata", "metadados")
_CAMPOS_ORIGEM = ("origem", "source", "document_name", "file_name", "title", "uri", "path")
_CAMPOS_SCORE = ("score", "similarity", "similarity_score", "distance")


def _ler(obj: Any, nomes: tuple[str, ...]) -> Any:
    """Le o primeiro campo que existir, seja `obj` um dict ou um objeto."""
    for nome in nomes:
        valor = obj.get(nome) if isinstance(obj, dict) else getattr(obj, nome, None)
        if valor is not None and valor != "":
            return valor
    return None


def _normalizar(resposta: Any, limite: int) -> list[Trecho]:
    """Transforma a resposta do SDK numa lista de `Trecho`."""
    bruto = resposta if isinstance(resposta, list) else _ler(resposta, _CAMPOS_LISTA)
    if not bruto:
        return []

    trechos: list[Trecho] = []
    for item in list(bruto)[:limite]:
        # Alguns SDKs devolvem so a string do trecho, sem envelope.
        texto = item if isinstance(item, str) else _ler(item, _CAMPOS_TEXTO)
        if not texto:
            continue

        metadados = _ler(item, _CAMPOS_METADADOS)
        origem = _ler(metadados, _CAMPOS_ORIGEM) if metadados is not None else None
        if origem is None and not isinstance(item, str):
            origem = _ler(item, _CAMPOS_ORIGEM)

        score = _ler(item, _CAMPOS_SCORE) if not isinstance(item, str) else None

        trechos.append(
            Trecho(
                texto=str(texto).strip(),
                origem=str(origem) if origem else "(origem nao informada)",
                score=float(score) if isinstance(score, (int, float)) else None,
            )
        )
    return trechos
