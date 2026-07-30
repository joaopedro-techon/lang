"""De qual LLM o agente fala -- e como trocar de provedor sem tocar no grafo.

Sao DOIS provedores, um para cada lugar onde o agente roda:

    AGENT_PROVIDER=iara         na empresa -- o gateway interno IaraGenAI (PADRAO)
    AGENT_PROVIDER=anthropic    fora da empresa -- Claude pela API da Anthropic

O grafo pede `build_llm()` e nao sabe (nem precisa saber) quem respondeu: os
dois entregam um chat model do LangChain, com a mesma interface
`.bind_tools()` / `.invoke()`, entao o loop ReAct continua igual.

Trocar e mexer no .env (ou rodar o /config, que reescreve as duas primeiras
linhas por voce e recarrega tudo na mesma sessao):

    AGENT_PROVIDER=iara               AGENT_PROVIDER=anthropic
    AGENT_MODEL=gpt-4.1-mini          AGENT_MODEL=claude-opus-5
    IARA_CLIENT_ID=...                ANTHROPIC_API_KEY=...
    IARA_CLIENT_SECRET=...

Os dois pacotes necessarios (`langchain-anthropic` e `langchain-openai`) vem no
install do custodia-cli. O `iaragenai`, que so o gateway usa, vem do Artifactory
interno -- fora da rede da empresa ele nao instala, e o provedor `iara` avisa
isso com todas as letras em vez de estourar um ImportError no meio da conversa.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any

# O modulo inteiro, e nao `from .config import AGENT_PROVIDER`: o /config
# reescreve o .env em runtime e manda o config recarregar. Um valor importado
# seria uma copia congelada no import -- o /status anunciaria o provedor
# antigo depois da troca.
from . import config
from .config import OPENAI_SENTINEL  # constante literal, essa nao muda
from .iara import IaraIndisponivel
from .iara import cliente as cliente_iara


class LLMIndisponivel(RuntimeError):
    """O modelo nao pode ser construido (provedor invalido, pacote, credencial)."""


def _ligar_gateway_iara() -> None:
    """Aponta o SDK da OpenAI para o gateway interno (IaraGenAI).

    O gateway nao e um endpoint compativel com a API da OpenAI -- nao adianta
    apontar `base_url` para ele. Ele entrega um CLIENTE proprio, a classe
    `IaraGenAI`, que imita a superficie do `openai.OpenAI` (`.chat.completions`)
    e cuida sozinho de autenticacao e roteamento para Azure/Bedrock/Vertex.

    Como o `ChatOpenAI` constroi o cliente dele por dentro
    (`openai.OpenAI(**client_params)`, sem parametro para injetar outro),
    a forma de encaixar o gateway e trocar a FABRICA: `openai.Client.__new__`
    passa a devolver um `IaraGenAI`. Como o objeto devolvido nao e instancia de
    `openai.OpenAI`, o Python nem chama o `__init__` original -- e o
    `ChatOpenAI` termina falando com o gateway sem saber disso.

    E um monkeypatch global e assumido: e o padrao que a propria organizacao
    usa (ver docs/exemplo_import/). Fica confinado a este provedor -- so roda
    com AGENT_PROVIDER=iara.
    """
    import openai  # vem junto com o langchain-openai

    # A sentinela e OBRIGATORIA aqui, e por um motivo que nao e obvio: sem
    # OPENAI_API_KEY no ambiente o ChatOpenAI nem chega a construir o cliente
    # (ele deixa `client=None` e so reclama na hora de invocar) -- ou seja, a
    # fabrica trocada logo abaixo nunca seria chamada e o gateway nunca
    # entraria na jogada. O sintoma seria um erro de "chave ausente" num
    # provedor que nao usa chave nenhuma.
    #
    # Repare que aqui SOBRESCREVEMOS, ao contrario da regra do config.py, que
    # preserva chave de verdade. Neste provedor quem autentica e o client_id/
    # client_secret do gateway: uma OPENAI_API_KEY real sobrando no ambiente
    # nao seria usada para nada -- so confundiria a leitura.
    os.environ["OPENAI_API_KEY"] = OPENAI_SENTINEL

    # Falha AGORA, com mensagem boa, se o SDK nao estiver instalado ou a
    # credencial nao passar -- em vez de estourar la dentro do construtor do
    # ChatOpenAI, embrulhado em erro de pydantic. Nao custa uma conexao a mais:
    # `iara.cliente()` guarda o cliente do processo, e a fabrica abaixo devolve
    # esse mesmo objeto.
    try:
        cliente_iara()
    except IaraIndisponivel as exc:
        raise LLMIndisponivel(str(exc)) from exc

    def _cliente_do_gateway(*_args: Any, **_kwargs: Any) -> Any:
        # Os argumentos que o langchain montaria (api_key, base_url,
        # http_client, timeout...) sao descartados de proposito: quem fala com
        # o modelo e o gateway, e ele se configura pelas proprias credenciais.
        return cliente_iara()

    # `openai.Client` e `openai.OpenAI` sao o MESMO objeto de classe (alias no
    # __init__ do SDK), entao um patch so cobre os dois nomes.
    openai.Client.__new__ = _cliente_do_gateway  # type: ignore[assignment]


@dataclass(frozen=True)
class Provedor:
    """Como instanciar o chat model de um provedor.

    O que os dois tem em comum fica fora daqui: `model`, `max_tokens` e
    `max_retries` se chamam igual no `ChatAnthropic` e no `ChatOpenAI`, entao
    o `build_llm` passa os tres direto. Sao campos so para o que DIVERGE.
    """

    nome: str
    rotulo: str
    modulo: str
    classe: str
    modelo_padrao: str
    # O que instalar quando o modulo nao existe.
    pacote: str
    # Credenciais obrigatorias, checadas antes de montar o grafo.
    variaveis_de_chave: tuple[str, ...] = ()
    # Variaveis que nao sao credencial mas ajustam ESTE provedor -- (nome,
    # nota). O /config as escreve no .env ja com o valor em uso, para que dar
    # de cara com elas no arquivo seja mais facil que descobrir no README que
    # elas existem. O valor sai do `config` na hora de escrever (o nome aqui e
    # o mesmo do atributo la), nunca de uma copia guardada neste catalogo.
    variaveis_opcionais: tuple[tuple[str, str], ...] = ()
    # Como esse SDK chama o endpoint alternativo (AGENT_BASE_URL). None = nao
    # aceita -- no gateway quem decide o endpoint e o proprio gateway.
    param_base_url: str | None = None
    # Passo extra ANTES de instanciar a classe, para o provedor que nao se
    # resolve so com kwargs. Hoje: o gateway interno, que troca a fabrica de
    # cliente do SDK da OpenAI.
    preparar: Callable[[], None] | None = field(default=None, repr=False)
    # Este provedor precisa que a gente PECA o cache de prompt? Na Anthropic
    # sim (o cache e opt-in). Do outro lado do gateway o cache, quando existe,
    # e do provedor de la -- pedir aqui nao ajuda e ainda pode virar erro.
    cache_explicito: bool = False


# O catalogo. Sao dois de proposito: a rede da empresa (gateway interno) e a
# maquina do desenvolvedor (Claude direto). Nada mais no projeto precisa saber
# disso -- a ORDEM aqui e a ordem que o /config oferece, entao o padrao vem
# primeiro.
PROVEDORES: dict[str, Provedor] = {
    "iara": Provedor(
        nome="iara",
        rotulo="IaraGenAI (gateway interno)",
        # Do ponto de vista do agente e um ChatOpenAI comum: quem desvia a
        # chamada para o gateway e o `preparar`, logo abaixo.
        modulo="langchain_openai",
        classe="ChatOpenAI",
        modelo_padrao="gpt-4.1-mini",
        pacote="langchain-openai",
        variaveis_de_chave=("IARA_CLIENT_ID", "IARA_CLIENT_SECRET"),
        # Endpoint e versao de API nao entram aqui: o gateway resolve os dois
        # a partir do IARA_ENVIRONMENT e do IARA_PROVIDER.
        variaveis_opcionais=(
            ("IARA_ENVIRONMENT", "dev | homol | prod"),
            (
                "IARA_PROVIDER",
                "quem serve o modelo por tras do gateway: "
                "azure_openai | bedrock | vertex",
            ),
        ),
        preparar=_ligar_gateway_iara,
    ),
    "anthropic": Provedor(
        nome="anthropic",
        rotulo="Anthropic (Claude)",
        modulo="langchain_anthropic",
        classe="ChatAnthropic",
        modelo_padrao="claude-opus-5",
        pacote="langchain-anthropic",
        variaveis_de_chave=("ANTHROPIC_API_KEY",),
        param_base_url="base_url",
        cache_explicito=True,
    ),
}

# Quem responde quando o .env nao diz nada. O gateway interno e o caminho
# normal na empresa, que e onde o agente roda de verdade.
PROVEDOR_PADRAO = "iara"


def provedor_atual() -> Provedor:
    """Traduz o AGENT_PROVIDER do .env numa entrada do catalogo."""
    nome = (config.AGENT_PROVIDER or PROVEDOR_PADRAO).strip().lower()
    provedor = PROVEDORES.get(nome)
    if provedor is None:
        raise LLMIndisponivel(
            f"AGENT_PROVIDER='{nome}' nao e um provedor conhecido.\n"
            f"Use um destes: {', '.join(sorted(PROVEDORES))}."
        )
    return provedor


def modelo_atual() -> str:
    """O modelo escolhido, ou o padrao do provedor se o .env nao disser."""
    return config.AGENT_MODEL.strip() or provedor_atual().modelo_padrao


def descrever_llm() -> str:
    """Uma linha legivel dizendo quem vai responder. Usado pelo /status."""
    try:
        provedor = provedor_atual()
    except LLMIndisponivel as exc:
        return f"configuracao invalida -- {exc}"
    texto = f"{provedor.rotulo} / {modelo_atual()}"
    if config.AGENT_BASE_URL and provedor.param_base_url:
        texto += f"  (via {config.AGENT_BASE_URL})"
    # Para qual ambiente o gateway aponta muda a resposta -- e a primeira
    # coisa que se quer saber quando o /status e chamado para conferir.
    if provedor.nome == "iara":
        texto += f"  ({config.IARA_ENVIRONMENT} / {config.IARA_PROVIDER})"
    return texto


def verificar_credenciais() -> str | None:
    """Devolve a mensagem do que falta -- ou None se esta tudo configurado.

    Checagem barata, feita ANTES de montar o grafo. Sem ela o desenvolvedor
    descobriria a chave faltando so quando o modelo fosse chamado, embrulhada
    num erro de SDK.
    """
    provedor = provedor_atual()
    faltando = [
        chave
        for chave in provedor.variaveis_de_chave
        if not (os.getenv(chave) or "").strip()
    ]
    if faltando:
        uma_so = len(faltando) == 1
        return (
            f"{' e '.join(faltando)} "
            f"{'nao definida' if uma_so else 'nao definidas'} "
            f"(AGENT_PROVIDER={provedor.nome}).\n"
            f"Copie o .env.example para .env e preencha "
            f"{'a credencial' if uma_so else 'as credenciais'}."
        )
    return None


def build_llm() -> Any:
    """Instancia o chat model do provedor configurado."""
    provedor = provedor_atual()

    faltando = verificar_credenciais()
    if faltando:
        raise LLMIndisponivel(faltando)

    try:
        modulo = import_module(provedor.modulo)
    except ImportError as exc:
        raise LLMIndisponivel(
            f"o pacote do provedor '{provedor.nome}' nao esta instalado.\n"
            f"Instale com: pip install {provedor.pacote}"
        ) from exc

    classe = getattr(modulo, provedor.classe)

    # Antes de instanciar: o provedor que precisa mexer no SDK faz isso agora
    # (hoje so o gateway interno). Se algo faltar, ele levanta LLMIndisponivel
    # com a mensagem certa.
    if provedor.preparar is not None:
        provedor.preparar()

    kwargs: dict[str, Any] = {
        "model": modelo_atual(),
        "max_tokens": config.AGENT_MAX_TOKENS,
        "max_retries": config.AGENT_MAX_RETRIES,
    }
    if config.AGENT_BASE_URL and provedor.param_base_url:
        kwargs[provedor.param_base_url] = config.AGENT_BASE_URL

    # `temperature` fica de fora de proposito: os modelos mais recentes da
    # Anthropic REJEITAM o parametro com HTTP 400. Como este arquivo serve os
    # dois provedores, nao passar e o unico comportamento que funciona nos
    # dois -- e o estilo da resposta se controla pelo prompt, nao por aqui.
    try:
        return classe(**kwargs)
    except Exception as exc:  # credencial invalida, parametro recusado, etc.
        raise LLMIndisponivel(
            f"nao foi possivel iniciar o modelo "
            f"({provedor.rotulo} / {modelo_atual()}): {exc}"
        ) from exc


def cache_ligado() -> bool:
    """O cache de prompt vai ser pedido nesta configuracao?"""
    return config.AGENT_PROMPT_CACHE and provedor_atual().cache_explicito


def build_llm_com_tools(ferramentas: list[Any]) -> Any:
    """O modelo pronto para o grafo: com ferramentas e cache de prompt.

    Sobre o CACHE. O loop ReAct reenvia system prompt + definicoes das
    ferramentas + historico inteiro a cada volta, e isso e o grosso da conta.
    Como o prefixo so cresce por append (nunca muda no meio), ele e o caso
    perfeito para cache: a partir da segunda volta o modelo rele o que ja
    conhece por uma fracao do preco e paga cheio so pelo trecho novo.

    Pedimos com `cache_control={"type": "ephemeral"}`, e so no Claude direto --
    o `cache_explicito` do catalogo diz quem aceita.

    A ORDEM abaixo importa e e facil errar: `bind_tools` PRIMEIRO, `bind`
    depois. Invertendo, o `bind_tools` seria resolvido no modelo original e
    devolveria um binding novo, jogando fora o `cache_control` -- sem erro
    nenhum, so uma conta que continua cara.
    """
    llm = build_llm().bind_tools(ferramentas)
    if cache_ligado():
        llm = llm.bind(cache_control={"type": "ephemeral"})
    return llm
