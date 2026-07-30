"""O cliente do gateway interno (SDK `iaragenai`), construido em um lugar so.

Dois consumidores bem diferentes usam o MESMO cliente:

* `llm.py` -- o modelo que responde na conversa. O `ChatOpenAI` conversa com o
  gateway achando que fala com a OpenAI (ver `_ligar_gateway_iara`).
* `conhecimento.py` -- a busca por similaridade na base vetorial.

Se cada um construisse o seu, seriam duas leituras de credencial para divergir
com o tempo -- alguem acrescenta o `environment` de um lado e esquece do outro,
e a KB passa a responder de um ambiente diferente do modelo. Entao a construcao
mora aqui, e cada chamador embrulha o erro no vocabulario dele (LLMIndisponivel
la, KBIndisponivel aqui).
"""

from __future__ import annotations

from typing import Any

# O modulo, nao os valores: o /config pode reescrever o .env em runtime, e um
# `from .config import IARA_CLIENT_ID` congelaria a credencial do import.
from . import config


class IaraIndisponivel(RuntimeError):
    """O cliente do gateway nao pode ser construido (pacote ou credencial)."""


# O cliente autentica ao nascer e a conversa faz varias chamadas (modelo e KB):
# construimos uma vez por processo.
_cache: Any = None


def cliente() -> Any:
    """O `IaraGenAI` do processo, construido na primeira chamada.

    Sem IARA_CLIENT_ID/SECRET chamamos o construtor VAZIO de proposito, em vez
    de recusar aqui: em algumas maquinas o proprio SDK resolve a credencial
    sozinho (helper da aplicacao, arquivo de configuracao). Se ele tambem nao
    conseguir, o erro que sobe e o dele -- que diz mais sobre o que falta do
    que um palpite nosso.
    """
    global _cache
    if _cache is not None:
        return _cache

    try:
        from iaragenai import IaraGenAI  # type: ignore[import-not-found]
    except ImportError as exc:
        raise IaraIndisponivel(
            "pacote 'iaragenai' nao instalado neste ambiente "
            "(vem do Artifactory interno). Instale com: pip install iaragenai"
        ) from exc

    credenciais: dict[str, Any] = {}
    if config.IARA_CLIENT_ID and config.IARA_CLIENT_SECRET:
        credenciais = {
            "client_id": config.IARA_CLIENT_ID,
            "client_secret": config.IARA_CLIENT_SECRET,
            "environment": config.IARA_ENVIRONMENT,
            "provider": config.IARA_PROVIDER,
        }

    try:
        _cache = IaraGenAI(**credenciais)
    except Exception as exc:
        raise IaraIndisponivel(
            f"nao foi possivel autenticar no gateway interno: {exc}"
        ) from exc
    return _cache


def esquecer_cliente() -> None:
    """Joga fora o cliente do processo -- o proximo uso constroi outro.

    Chamado quando o /config mexe no .env: credencial ou ambiente novos pedem
    um cliente novo, senao a conversa continuaria autenticada no ambiente
    anterior sem nenhum sinal disso na tela.
    """
    global _cache
    _cache = None
