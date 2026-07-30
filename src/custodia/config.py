"""Configuracao central do agente.

Todo `os.getenv` do projeto passa por aqui, e nao e so organizacao: e este
arquivo que chama `load_dotenv()`. Um modulo que lesse o ambiente por conta
propria, antes de importar este, leria o ambiente ANTES do .env ser carregado
-- e enxergaria variavel vazia sem motivo aparente.

O `project_root` e um estado global do processo: definimos ele uma vez
(no `main.py`, a partir do argumento de linha de comando) e as ferramentas
em `tools.py` resolvem todos os caminhos contra ele. Isso garante que o
agente so consiga ler/escrever DENTRO do projeto Spring Boot alvo.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Procura o .env primeiro na pasta onde o dev rodou o comando, depois na do
# proprio pacote. Sem o primeiro, uma instalacao normal (site-packages) nunca
# enxergaria o .env do repositorio do desenvolvedor -- so o `pip install -e .`
# funcionaria, porque ali o pacote MORA no repositorio.
load_dotenv(find_dotenv(usecwd=True))
load_dotenv()

# Sentinela da OPENAI_API_KEY.
#
# Clientes compativeis com a API da OpenAI costumam EXIGIR que a variavel
# exista -- eles recusam inicializar sem ela -- mesmo quando o endpoint do
# outro lado nao autentica nada. Como a exigencia vem da BIBLIOTECA e nao do
# modelo escolhido, ela vale para qualquer AGENT_PROVIDER: um projeto rodando
# em Claude pode importar uma lib que estoura no import por falta dessa chave.
#
# Se ja houver chave de verdade no ambiente ou no .env, ela ganha: a sentinela
# so preenche o vazio, nunca sobrescreve credencial.
#
# Repare que a checagem NAO e um `setdefault`. Na maquina corporativa a
# credencial costuma vir de variavel de ambiente da CONTA do usuario, e quem
# configura a AZURE_OPENAI_API_KEY por la quase nunca configura a OPENAI_API_KEY
# junto -- pior, e comum sobrar uma OPENAI_API_KEY VAZIA de alguma tentativa
# anterior. String vazia existe para o `setdefault` (ele nao preencheria) mas
# nao serve para a biblioteca. Por isso tratamos vazio como ausente.
OPENAI_SENTINEL = "sk-no-key-required"
if not (os.getenv("OPENAI_API_KEY") or "").strip():
    os.environ["OPENAI_API_KEY"] = OPENAI_SENTINEL

def _inteiro(nome: str, padrao: int) -> int:
    """Le um inteiro do ambiente sem derrubar a CLI se vier lixo no .env.

    Um typo em KB_TOP_K nao deveria impedir o /initialize de rodar, entao
    caimos no padrao em silencio em vez de estourar no import.
    """
    bruto = os.getenv(nome)
    if not bruto:
        return padrao
    try:
        return int(bruto)
    except ValueError:
        return padrao


def _booleano(nome: str, padrao: bool) -> bool:
    """Le uma flag do ambiente. Ausente ou vazia = o padrao."""
    bruto = os.getenv(nome)
    if not bruto:
        return padrao
    return bruto.strip().lower() in ("1", "true", "sim", "yes", "on")


# ---------------------------------------------------------------------------
# O LLM
# ---------------------------------------------------------------------------
# O catalogo de provedores esta em `llm.py`; aqui so lemos a escolha do .env.

# Quem responde: anthropic, openai, azure, google, bedrock, ollama.
AGENT_PROVIDER: str = os.getenv("AGENT_PROVIDER", "anthropic")

# Modelo. Vazio = usa o padrao do provedor escolhido (ver `llm.PROVEDORES`).
AGENT_MODEL: str = os.getenv("AGENT_MODEL", "")

# Teto de tokens da resposta do modelo.
AGENT_MAX_TOKENS: int = _inteiro("AGENT_MAX_TOKENS", 16_000)

# Quantas vezes o SDK repete uma chamada que falhou por motivo transitorio
# (429, 5xx, queda de conexao). O padrao dos SDKs e 2, que nao segura pico de
# sobrecarga do provedor -- e no loop ReAct uma volta que morre joga fora o
# turno inteiro, entao vale insistir mais.
AGENT_MAX_RETRIES: int = _inteiro("AGENT_MAX_RETRIES", 6)

# Endpoint alternativo: e por aqui que se aponta para um gateway interno
# compativel com a API do provedor. Vazio = endpoint publico padrao.
AGENT_BASE_URL: str = os.getenv("AGENT_BASE_URL", "")

# Cache de prompt. O loop ReAct reenvia todo o historico a cada volta, entao
# cachear o prefixo e o que mais corta custo aqui. Desligue so para comparar
# o gasto com e sem (o /chat mostra os tokens de cache no fim de cada turno).
AGENT_PROMPT_CACHE: bool = _booleano("AGENT_PROMPT_CACHE", True)

# Versao da API do Azure OpenAI (AGENT_PROVIDER=azure).
#
# O `AzureChatOpenAI` RECUSA nascer sem isso -- o erro e um ValidationError
# pedindo "either the `api_version` argument or the `OPENAI_API_VERSION`
# environment variable". Diferente dos outros provedores, no Azure a versao da
# API e do endpoint, nao do modelo, entao nao da para inferir do AGENT_MODEL.
# Um padrao GA aqui deixa o caso comum funcionar sem mais uma variavel no .env;
# quem precisa de um recurso mais novo (ou de um endpoint preso a outra versao)
# sobrescreve.
AZURE_OPENAI_API_VERSION: str = (
    os.getenv("AZURE_OPENAI_API_VERSION")
    or os.getenv("OPENAI_API_VERSION")
    or "2024-10-21"
)
# Espelhado no ambiente pelo mesmo motivo da sentinela acima: bibliotecas que
# falam Azure OpenAI leem essa variavel direto, sem passar por este modulo.
os.environ.setdefault("OPENAI_API_VERSION", AZURE_OPENAI_API_VERSION)


# ---------------------------------------------------------------------------
# Gateway interno IaraGenAI (AGENT_PROVIDER=iara)
# ---------------------------------------------------------------------------
# O gateway nao usa chave de modelo: a autenticacao e client_id/client_secret,
# e o modelo do outro lado e escolhido por `provider` + AGENT_MODEL.
#
# NUNCA coloque o secret no codigo -- ele mora no .env (que esta no
# .gitignore) ou na variavel de ambiente da conta do usuario.
IARA_CLIENT_ID: str = os.getenv("IARA_CLIENT_ID", "")
IARA_CLIENT_SECRET: str = os.getenv("IARA_CLIENT_SECRET", "")
# dev | homol | prod
IARA_ENVIRONMENT: str = os.getenv("IARA_ENVIRONMENT", "dev")
# Quem serve o modelo POR TRAS do gateway: azure_openai | bedrock | vertex.
IARA_PROVIDER: str = os.getenv("IARA_PROVIDER", "azure_openai")


# ---------------------------------------------------------------------------
# A base de conhecimento (RAG)
# ---------------------------------------------------------------------------
# Identificadores da KB na solucao interna de embedding. Sem KB_ID a ferramenta
# `buscar_conhecimento` se declara indisponivel, em vez de falhar no meio da
# conversa.

KB_ID: str = os.getenv("KB_ID", "")
# Versao fixa da KB. Vazio = a solucao interna decide (normalmente a atual).
KB_VERSION_ID: str = os.getenv("KB_VERSION_ID", "")
# Quantos trechos trazer por busca. Mais que isso costuma so inflar o contexto.
KB_TOP_K: int = _inteiro("KB_TOP_K", 5)

# Raiz do projeto Spring Boot que o agente vai configurar.
# Definido em runtime via set_project_root().
_project_root: Path | None = None

# Modo de auto-aprovacao: quando True, as ferramentas destrutivas
# (write_file, run_maven) NAO pedem confirmacao. Ligado pela flag --yes.
_auto_approve: bool = False


def set_auto_approve(value: bool) -> None:
    """Liga/desliga a auto-aprovacao (pular confirmacoes)."""
    global _auto_approve
    _auto_approve = value


def is_auto_approve() -> bool:
    return _auto_approve


def set_project_root(path: str | os.PathLike[str]) -> Path:
    """Define (uma vez) a pasta do projeto Spring Boot alvo."""
    global _project_root
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        raise NotADirectoryError(f"Nao e um diretorio valido: {resolved}")
    _project_root = resolved
    return resolved


def get_project_root() -> Path:
    if _project_root is None:
        raise RuntimeError(
            "project_root nao definido. Chame set_project_root() antes de usar as tools."
        )
    return _project_root


def resolve_inside_project(relative_or_absolute: str) -> Path:
    """Resolve um caminho e garante que ele fica dentro do projeto.

    Barreira de seguranca: impede que o agente escape da pasta alvo
    (via '..', symlinks ou caminhos absolutos externos).
    """
    root = get_project_root()
    candidate = (root / relative_or_absolute).resolve()
    if root != candidate and root not in candidate.parents:
        raise PermissionError(
            f"Caminho fora do projeto e bloqueado: {relative_or_absolute}"
        )
    return candidate
