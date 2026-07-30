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
# exista -- eles recusam inicializar sem ela -- mesmo quando quem autentica e
# outra coisa. E o caso do gateway interno: ele usa o `ChatOpenAI` como fachada
# (ver `llm.py`), e sem essa variavel o cliente nem nasce. Como a exigencia vem
# da BIBLIOTECA e nao do modelo, preenchemos para qualquer AGENT_PROVIDER: um
# projeto rodando em Claude pode importar uma lib que estoura no import por
# falta dessa chave.
#
# Se ja houver chave de verdade no ambiente ou no .env, ela ganha aqui: a
# sentinela so preenche o vazio. (No provedor `iara` o llm.py sobrescreve de
# proposito -- la uma chave real nao serviria para nada.)
#
# Repare que a checagem NAO e um `setdefault`. Na maquina corporativa e comum
# sobrar uma OPENAI_API_KEY VAZIA de alguma tentativa anterior: string vazia
# existe para o `setdefault` (que entao nao preencheria) mas nao serve para a
# biblioteca. Por isso tratamos vazio como ausente.
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
# O que vem do ambiente
# ---------------------------------------------------------------------------
# Estas variaveis sao lidas no import E de novo quando o /config reescreve o
# .env (ver `recarregar`). Por isso a leitura mora numa funcao, e nao solta no
# corpo do modulo: sem isso, trocar de provedor so valeria na proxima vez que a
# CLI subisse -- e o /status continuaria anunciando o modelo antigo.
#
# ATENCAO para quem for consumir daqui: importe o MODULO, nao o valor.
#
#     from . import config      -> config.AGENT_PROVIDER  (le o valor atual)
#     from .config import AGENT_PROVIDER   # NAO: copia o valor do import
#
# O `from X import valor` congela o que existia no momento do import, e nenhum
# recarregamento alcanca essa copia.

# O catalogo de provedores esta em `llm.py`; aqui so lemos a escolha do .env.

# Quem responde: iara (gateway interno, o padrao) ou anthropic (Claude direto).
AGENT_PROVIDER: str = ""
# Modelo. Vazio = usa o padrao do provedor escolhido (ver `llm.PROVEDORES`).
AGENT_MODEL: str = ""
# Teto de tokens da resposta do modelo.
AGENT_MAX_TOKENS: int = 0
# Quantas vezes o SDK repete uma chamada que falhou por motivo transitorio
# (429, 5xx, queda de conexao). O padrao dos SDKs e 2, que nao segura pico de
# sobrecarga do provedor -- e no loop ReAct uma volta que morre joga fora o
# turno inteiro, entao vale insistir mais.
AGENT_MAX_RETRIES: int = 0
# Endpoint alternativo do Claude. Vazio = endpoint publico padrao.
AGENT_BASE_URL: str = ""
# Cache de prompt. O loop ReAct reenvia todo o historico a cada volta, entao
# cachear o prefixo e o que mais corta custo aqui. Desligue so para comparar
# o gasto com e sem (o /chat mostra os tokens de cache no fim de cada turno).
AGENT_PROMPT_CACHE: bool = True

# Gateway interno IaraGenAI (AGENT_PROVIDER=iara). Ele nao usa chave de
# modelo: a autenticacao e client_id/client_secret, e o modelo do outro lado
# sai de `provider` + AGENT_MODEL.
#
# NUNCA coloque o secret no codigo -- ele mora no .env (que esta no
# .gitignore) ou na variavel de ambiente da conta do usuario.
IARA_CLIENT_ID: str = ""
IARA_CLIENT_SECRET: str = ""
# dev | homol | prod
IARA_ENVIRONMENT: str = ""
# Quem serve o modelo POR TRAS do gateway: azure_openai | bedrock | vertex.
IARA_PROVIDER: str = ""

# Identificadores da KB na solucao interna de embedding. Sem KB_ID a ferramenta
# `buscar_conhecimento` se declara indisponivel, em vez de falhar no meio da
# conversa.
KB_ID: str = ""
# Versao fixa da KB. Vazio = a solucao interna decide (normalmente a atual).
KB_VERSION_ID: str = ""
# Quantos trechos trazer por busca. Mais que isso costuma so inflar o contexto.
KB_TOP_K: int = 5


def _ler_ambiente() -> None:
    """Passa o ambiente para as variaveis acima."""
    global AGENT_PROVIDER, AGENT_MODEL, AGENT_MAX_TOKENS, AGENT_MAX_RETRIES
    global AGENT_BASE_URL, AGENT_PROMPT_CACHE
    global IARA_CLIENT_ID, IARA_CLIENT_SECRET, IARA_ENVIRONMENT, IARA_PROVIDER
    global KB_ID, KB_VERSION_ID, KB_TOP_K

    AGENT_PROVIDER = os.getenv("AGENT_PROVIDER", "iara")
    AGENT_MODEL = os.getenv("AGENT_MODEL", "")
    AGENT_MAX_TOKENS = _inteiro("AGENT_MAX_TOKENS", 16_000)
    AGENT_MAX_RETRIES = _inteiro("AGENT_MAX_RETRIES", 6)
    AGENT_BASE_URL = os.getenv("AGENT_BASE_URL", "")
    AGENT_PROMPT_CACHE = _booleano("AGENT_PROMPT_CACHE", True)

    IARA_CLIENT_ID = os.getenv("IARA_CLIENT_ID", "")
    IARA_CLIENT_SECRET = os.getenv("IARA_CLIENT_SECRET", "")
    IARA_ENVIRONMENT = os.getenv("IARA_ENVIRONMENT", "dev")
    IARA_PROVIDER = os.getenv("IARA_PROVIDER", "azure_openai")

    KB_ID = os.getenv("KB_ID", "")
    KB_VERSION_ID = os.getenv("KB_VERSION_ID", "")
    KB_TOP_K = _inteiro("KB_TOP_K", 5)


_ler_ambiente()


def recarregar() -> None:
    """Rele o .env do disco e atualiza tudo que veio dele.

    Chamado pelo /config depois de escrever o arquivo, para que a troca de
    provedor valha JA -- sem isso o /status e a proxima conversa continuariam
    com o que foi lido quando a CLI subiu.

    Aqui o `override=True` e proposital, ao contrario do carregamento inicial:
    o .env acabou de ser escrito pelo proprio agente, entao ele e a fonte da
    verdade -- mais recente que qualquer valor que ja estivesse no ambiente.
    """
    load_dotenv(find_dotenv(usecwd=True), override=True)
    _ler_ambiente()

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
