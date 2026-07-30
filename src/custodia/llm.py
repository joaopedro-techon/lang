"""De qual LLM o agente fala -- e como trocar de provedor sem tocar no grafo.

O agente nasceu preso ao Claude: o `graph.py` instanciava `ChatAnthropic`
direto. Isso incomoda em ambiente corporativo, onde o modelo disponivel muda
por politica, por custo ou porque a empresa expoe um gateway proprio.

Aqui centralizamos essa escolha. O grafo pede `build_llm()` e nao sabe (nem
precisa saber) quem respondeu: todo chat model do LangChain expoe a mesma
interface `.bind_tools()` / `.invoke()`, entao o loop ReAct continua igual.

Trocar de provedor e mexer no .env:

    AGENT_PROVIDER=openai
    AGENT_MODEL=gpt-4o
    OPENAI_API_KEY=...

Os pacotes de cada provedor sao OPCIONAIS e importados sob demanda: quem usa
Claude nao precisa ter o SDK da OpenAI instalado. Quando falta um, a mensagem
de erro diz exatamente qual `pip install` resolve -- e nao um ImportError cru
no meio da conversa.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from .config import (
    AGENT_BASE_URL,
    AGENT_MAX_RETRIES,
    AGENT_MAX_TOKENS,
    AGENT_MODEL,
    AGENT_PROMPT_CACHE,
    AGENT_PROVIDER,
)


class LLMIndisponivel(RuntimeError):
    """O modelo nao pode ser construido (provedor invalido, pacote, credencial)."""


@dataclass(frozen=True)
class Provedor:
    """Como instanciar o chat model de um provedor.

    Os campos `param_*` existem porque cada SDK batizou a mesma coisa de um
    jeito: teto de tokens e `max_tokens` na Anthropic, `max_output_tokens` no
    Gemini e `num_predict` no Ollama. Declarar o nome aqui evita um `if` por
    provedor la embaixo no `build_llm`.
    """

    nome: str
    rotulo: str
    modulo: str
    classe: str
    modelo_padrao: str
    # O que instalar quando o modulo nao existe.
    pacote: str
    # Credencial obrigatoria. None = o SDK resolve sozinho (profile da AWS,
    # servidor local...).
    variavel_de_chave: str | None = None
    param_modelo: str = "model"
    param_max_tokens: str | None = "max_tokens"
    # Retentativa automatica do SDK. None = este SDK nao expoe o parametro
    # (o Bedrock configura isso no boto3, o Ollama e local) -- passar ali
    # levantaria erro de campo desconhecido.
    param_max_retries: str | None = "max_retries"
    # Como esse SDK chama o endpoint alternativo. None = nao aceita.
    param_base_url: str | None = None
    # Este provedor precisa que a gente PECA o cache de prompt? Na Anthropic
    # sim (o cache e opt-in). OpenAI e Google cacheiam prefixo sozinhos, sem
    # parametro nenhum -- pedir la nao ajuda e ainda pode virar erro.
    cache_explicito: bool = False


# O catalogo. Acrescentar um provedor e acrescentar uma entrada aqui -- nada
# mais no projeto precisa mudar.
PROVEDORES: dict[str, Provedor] = {
    "anthropic": Provedor(
        nome="anthropic",
        rotulo="Anthropic (Claude)",
        modulo="langchain_anthropic",
        classe="ChatAnthropic",
        modelo_padrao="claude-opus-5",
        pacote="langchain-anthropic",
        variavel_de_chave="ANTHROPIC_API_KEY",
        param_base_url="base_url",
        cache_explicito=True,
    ),
    "openai": Provedor(
        nome="openai",
        rotulo="OpenAI",
        modulo="langchain_openai",
        classe="ChatOpenAI",
        modelo_padrao="gpt-4o",
        pacote="langchain-openai",
        variavel_de_chave="OPENAI_API_KEY",
        param_base_url="base_url",
    ),
    "azure": Provedor(
        nome="azure",
        rotulo="Azure OpenAI",
        modulo="langchain_openai",
        classe="AzureChatOpenAI",
        modelo_padrao="gpt-4o",
        pacote="langchain-openai",
        variavel_de_chave="AZURE_OPENAI_API_KEY",
        # No Azure nao se endereca o modelo, e sim o DEPLOYMENT: o AGENT_MODEL
        # aqui e o nome do deployment criado no portal.
        param_modelo="azure_deployment",
        param_base_url="azure_endpoint",
    ),
    "google": Provedor(
        nome="google",
        rotulo="Google (Gemini)",
        modulo="langchain_google_genai",
        classe="ChatGoogleGenerativeAI",
        modelo_padrao="gemini-2.5-pro",
        pacote="langchain-google-genai",
        variavel_de_chave="GOOGLE_API_KEY",
        param_max_tokens="max_output_tokens",
    ),
    "bedrock": Provedor(
        nome="bedrock",
        rotulo="AWS Bedrock",
        modulo="langchain_aws",
        classe="ChatBedrockConverse",
        modelo_padrao="anthropic.claude-opus-5",
        pacote="langchain-aws",
        # Credencial vem do profile/role da AWS, como no resto do agente.
        variavel_de_chave=None,
        # Modelo Claude servido pela AWS: o cache continua sendo opt-in.
        cache_explicito=True,
        param_max_retries=None,
    ),
    "ollama": Provedor(
        nome="ollama",
        rotulo="Ollama (local)",
        modulo="langchain_ollama",
        classe="ChatOllama",
        modelo_padrao="qwen3:8b",
        pacote="langchain-ollama",
        variavel_de_chave=None,
        param_max_tokens="num_predict",
        param_base_url="base_url",
        param_max_retries=None,
    ),
}


def provedor_atual() -> Provedor:
    """Traduz o AGENT_PROVIDER do .env numa entrada do catalogo."""
    nome = (AGENT_PROVIDER or "anthropic").strip().lower()
    provedor = PROVEDORES.get(nome)
    if provedor is None:
        raise LLMIndisponivel(
            f"AGENT_PROVIDER='{nome}' nao e um provedor conhecido.\n"
            f"Use um destes: {', '.join(sorted(PROVEDORES))}."
        )
    return provedor


def modelo_atual() -> str:
    """O modelo escolhido, ou o padrao do provedor se o .env nao disser."""
    return AGENT_MODEL.strip() or provedor_atual().modelo_padrao


def descrever_llm() -> str:
    """Uma linha legivel dizendo quem vai responder. Usado pelo /status."""
    try:
        provedor = provedor_atual()
    except LLMIndisponivel as exc:
        return f"configuracao invalida -- {exc}"
    texto = f"{provedor.rotulo} / {modelo_atual()}"
    if AGENT_BASE_URL and provedor.param_base_url:
        texto += f"  (via {AGENT_BASE_URL})"
    return texto


def verificar_credenciais() -> str | None:
    """Devolve a mensagem do que falta -- ou None se esta tudo configurado.

    Checagem barata, feita ANTES de montar o grafo. Sem ela o desenvolvedor
    descobriria a chave faltando so quando o modelo fosse chamado, embrulhada
    num erro de SDK. Provedores sem `variavel_de_chave` (Bedrock, Ollama)
    passam direto: quem valida a credencial deles e o proprio SDK.
    """
    provedor = provedor_atual()
    chave = provedor.variavel_de_chave
    if chave and not os.getenv(chave):
        return (
            f"{chave} nao definida (AGENT_PROVIDER={provedor.nome}).\n"
            "Copie o .env.example para .env e preencha a credencial."
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

    kwargs: dict[str, Any] = {provedor.param_modelo: modelo_atual()}
    if provedor.param_max_tokens:
        kwargs[provedor.param_max_tokens] = AGENT_MAX_TOKENS
    if provedor.param_max_retries:
        kwargs[provedor.param_max_retries] = AGENT_MAX_RETRIES
    if AGENT_BASE_URL and provedor.param_base_url:
        kwargs[provedor.param_base_url] = AGENT_BASE_URL

    # `temperature` fica de fora de proposito: os modelos mais recentes da
    # Anthropic REJEITAM o parametro com HTTP 400. Como este arquivo serve
    # todos os provedores, nao passar e o unico comportamento que funciona em
    # todos -- e o estilo da resposta se controla pelo prompt, nao por aqui.
    try:
        return classe(**kwargs)
    except Exception as exc:  # credencial invalida, parametro recusado, etc.
        raise LLMIndisponivel(
            f"nao foi possivel iniciar o modelo "
            f"({provedor.rotulo} / {modelo_atual()}): {exc}"
        ) from exc


def cache_ligado() -> bool:
    """O cache de prompt vai ser pedido nesta configuracao?"""
    return AGENT_PROMPT_CACHE and provedor_atual().cache_explicito


def build_llm_com_tools(ferramentas: list[Any]) -> Any:
    """O modelo pronto para o grafo: com ferramentas e cache de prompt.

    Sobre o CACHE. O loop ReAct reenvia system prompt + definicoes das
    ferramentas + historico inteiro a cada volta, e isso e o grosso da conta.
    Como o prefixo so cresce por append (nunca muda no meio), ele e o caso
    perfeito para cache: a partir da segunda volta o modelo rele o que ja
    conhece por uma fracao do preco e paga cheio so pelo trecho novo.

    Pedimos com `cache_control={"type": "ephemeral"}`. O langchain-anthropic
    resolve a diferenca de transporte sozinho: na API direta isso vira o
    parametro top-level (que marca o ultimo bloco cacheavel, ou seja, todo o
    prefixo), e no Bedrock ele expande para um breakpoint no bloco -- a unica
    forma que aquele transporte aceita.

    A ORDEM abaixo importa e e facil errar: `bind_tools` PRIMEIRO, `bind`
    depois. Invertendo, o `bind_tools` seria resolvido no modelo original e
    devolveria um binding novo, jogando fora o `cache_control` -- sem erro
    nenhum, so uma conta que continua cara.
    """
    llm = build_llm().bind_tools(ferramentas)
    if cache_ligado():
        llm = llm.bind(cache_control={"type": "ephemeral"})
    return llm
