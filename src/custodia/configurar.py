"""O /config: prepara o que o agente precisa e que mora FORA do repositorio.

Duas configuracoes nunca estao no git, e por isso sao sempre as que faltam: as
credenciais (`.env`) e os perfis da AWS (`~/.aws/config`). Quem chega no time
descobre as duas por tentativa e erro, lendo mensagem de erro.

Este arquivo cria o ESQUELETO das duas -- com os nomes certos, na sintaxe
certa, com comentario dizendo o que preencher. Os valores de verdade (chave,
URL de SSO, id da conta) sao do desenvolvedor: o agente nao os inventa nem os
adivinha.

Duas regras valem para tudo aqui, e as duas existem pelo mesmo motivo -- estes
arquivos NAO sao nossos:

1. NUNCA sobrescrever o que ja existe. O ~/.aws/config tem os perfis dos outros
   projetos da pessoa, e o .env pode ter chave de verdade. So ACRESCENTAMOS o
   que falta, e rodar /config duas vezes na segunda nao faz nada.
2. BACKUP antes de tocar em arquivo fora do projeto. Escrever no home de
   alguem sem rede de seguranca nao se faz.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dotenv import find_dotenv

from . import config
from .aws import PERFIS, REGIAO_PADRAO
from .config import OPENAI_SENTINEL
from .llm import PROVEDORES
from .questions import Option, Question

# Valor que marca "isto aqui e voce que preenche". Aparece so em linha
# comentada -- ver `_render_env`.
PLACEHOLDER = "PREENCHA"


# ---------------------------------------------------------------------------
# As perguntas
# ---------------------------------------------------------------------------
# Ficam aqui, e nao no `questions.py`, porque a lista de provedores e montada a
# partir do catalogo do `llm.py`. Deixar isso no questions.py acoplaria o
# catalogo de perguntas do /initialize (que e dado puro) ao modulo de LLM.

Q_PROVEDOR = Question(
    id="provedor",
    kind="choice",
    title="Qual provedor de LLM este ambiente vai usar?",
    help="Define AGENT_PROVIDER e qual credencial entra no .env.",
    options=tuple(
        Option(
            value=p.nome,
            label=p.rotulo,
            description=(
                f"modelo padrao: {p.modelo_padrao}"
                + (
                    f" | chave: {' + '.join(p.variaveis_de_chave)}"
                    if p.variaveis_de_chave
                    else " | sem chave"
                )
            ),
        )
        for p in PROVEDORES.values()
    ),
)

Q_AMBIENTES = Question(
    id="ambientes",
    kind="multi_choice",
    title="Para quais ambientes criar o esqueleto de perfil da AWS?",
    help=(
        "Cria a entrada com o nome que o /infra espera.\n"
        "Perfis que voce ja tem sao preservados como estao."
    ),
    options=tuple(
        Option(value=ambiente, label=f"{ambiente}  ({perfil})")
        for ambiente, perfil in PERFIS.items()
    ),
    allow_empty=True,
)

Q_METODO_AWS = Question(
    id="metodo_aws",
    kind="choice",
    title="Como a area autentica na AWS?",
    help="Decide o que entra no ~/.aws/config e se o ~/.aws/credentials e usado.",
    options=(
        Option(
            value="sso",
            label="SSO (aws sso login)",
            description="Tudo fica no config; o credentials nao e usado. Credencial temporaria.",
        ),
        Option(
            value="chave",
            label="Chave estatica (access key / secret key)",
            description="Precisa do credentials. Chave de longa duracao, em texto puro no disco.",
        ),
    ),
)


def Q_CONFIRMAR(quantidade: int) -> Question:
    return Question(
        id="confirmar",
        kind="confirm",
        title=f"Aplicar as {quantidade} mudanca(s) acima?",
    )


# ---------------------------------------------------------------------------
# O .env
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Chave:
    """Uma linha do .env que o agente precisa.

    `comentada=True` para segredo e identificador que so o desenvolvedor sabe.
    Nao e frescura: uma chave escrita como `OPENAI_API_KEY=PREENCHA` PASSARIA
    na checagem de credencial do `llm.py` (a variavel existe) e so falharia
    depois, como 401 no meio da conversa. Comentada, a variavel simplesmente
    nao existe -- e o agente diz "OPENAI_API_KEY nao definida", que e a
    mensagem util.
    """

    nome: str
    valor: str
    comentada: bool = False
    nota: str = ""
    # A linha ja existe no arquivo com outro valor -- reescrever ou respeitar?
    # A regra geral e RESPEITAR: o .env e do desenvolvedor, e o /config so
    # completa o que falta. A excecao e a escolha que ele acabou de fazer no
    # wizard (o provedor e o modelo dele): ali, deixar o valor antigo seria
    # ignorar a resposta e devolver um arquivo que contradiz o que foi pedido.
    substituir: bool = False


@dataclass
class PlanoDoEnv:
    caminho: Path
    faltando: list[Chave] = field(default_factory=list)
    # (chave nova, valor que estava la) -- linhas que vao ser reescritas.
    substituindo: list[tuple[Chave, str]] = field(default_factory=list)
    ja_configuradas: list[str] = field(default_factory=list)

    @property
    def tem_o_que_fazer(self) -> bool:
        return bool(self.faltando or self.substituindo)


def caminho_do_env() -> Path:
    """Onde escrever o .env.

    Reaproveita a MESMA busca que o `config.py` usa para carregar (do diretorio
    atual para cima). Se ja existe um .env sendo lido, e nele que mexemos --
    criar um segundo mais perto do cwd deixaria dois arquivos disputando, e o
    que o agente le nao seria o que o /config acabou de escrever.
    """
    encontrado = find_dotenv(usecwd=True)
    return Path(encontrado) if encontrado else Path.cwd() / ".env"


def _chaves_necessarias(provedor_nome: str) -> list[Chave]:
    provedor = PROVEDORES[provedor_nome]
    # Trocar de provedor obriga a reescrever as duas primeiras linhas: sem
    # isso, escolher outra LLM no wizard nao mudaria nada -- o arquivo ja tem
    # um AGENT_PROVIDER, e a regra normal e nao mexer no que ja existe. Se a
    # escolha foi o provedor que ja estava valendo, nada e reescrito e um
    # AGENT_MODEL customizado sobrevive.
    trocou_de_provedor = (config.AGENT_PROVIDER or "").strip().lower() != provedor.nome
    chaves = [
        Chave(
            "AGENT_PROVIDER",
            provedor.nome,
            nota="quem responde",
            substituir=trocou_de_provedor,
        ),
        Chave(
            "AGENT_MODEL",
            provedor.modelo_padrao,
            nota="vazio = padrao do provedor",
            substituir=trocou_de_provedor,
        ),
        # Entra SEMPRE, em qualquer provedor -- a exigencia vem da biblioteca
        # cliente, nao do modelo. Ver OPENAI_SENTINEL no config.py.
        Chave(
            "OPENAI_API_KEY",
            OPENAI_SENTINEL,
            nota="sentinela exigida por clientes compativeis com a API da OpenAI",
        ),
    ]
    # As credenciais do provedor, menos a OPENAI_API_KEY -- ela ja entrou
    # acima, e repetir deixaria a mesma variavel duas vezes no arquivo, uma
    # ativa e uma comentada.
    for variavel in provedor.variaveis_de_chave:
        if variavel == "OPENAI_API_KEY":
            continue
        chaves.append(
            Chave(
                variavel,
                PLACEHOLDER,
                comentada=True,
                nota=f"credencial do {provedor.rotulo} -- descomente e cole a sua",
            )
        )
    # Os ajustes proprios do provedor (ambiente do gateway, por exemplo), ja
    # com o valor que o agente usa AGORA -- lido do config na hora, para o
    # arquivo escrito nao discordar do que o /status mostra em seguida.
    for variavel, nota in provedor.variaveis_opcionais:
        chaves.append(Chave(variavel, str(getattr(config, variavel, "")), nota=nota))
    chaves.append(
        Chave("KB_ID", PLACEHOLDER, comentada=True, nota="id da KB na solucao interna de embedding")
    )
    chaves.append(
        Chave("KB_VERSION_ID", PLACEHOLDER, comentada=True, nota="opcional: fixa a versao da KB")
    )
    return chaves


def _chaves_ja_definidas(texto: str) -> dict[str, str]:
    """Nome -> valor de tudo que ja esta no arquivo, comentado ou nao.

    Conta a linha comentada de proposito: se o /config ja escreveu
    `# OPENAI_API_KEY=PREENCHA` antes, escrever de novo criaria uma segunda
    linha igual a cada execucao.
    """
    encontradas: dict[str, str] = {}
    for linha in texto.splitlines():
        limpa = linha.strip().lstrip("#").strip()
        if "=" in limpa:
            nome, valor = limpa.split("=", 1)
            encontradas[nome.strip()] = valor.strip()
    return encontradas


def planejar_env(provedor_nome: str) -> PlanoDoEnv:
    caminho = caminho_do_env()
    texto = caminho.read_text(encoding="utf-8") if caminho.is_file() else ""
    existentes = _chaves_ja_definidas(texto)

    plano = PlanoDoEnv(caminho=caminho)
    for chave in _chaves_necessarias(provedor_nome):
        if chave.nome.startswith("#"):
            continue  # linha puramente informativa, nao e chave
        if chave.nome not in existentes:
            plano.faltando.append(chave)
            continue
        anterior = existentes[chave.nome]
        if chave.substituir and anterior != chave.valor:
            plano.substituindo.append((chave, anterior))
        else:
            plano.ja_configuradas.append(chave.nome)
    return plano


def _render_env(chaves: list[Chave]) -> str:
    linhas = [
        "",
        f"# --- adicionado pelo /config em {_agora()} ---",
    ]
    for chave in chaves:
        if chave.nota:
            linhas.append(f"# {chave.nota}")
        prefixo = "# " if chave.comentada else ""
        linhas.append(f"{prefixo}{chave.nome}={chave.valor}")
    linhas.append("")
    return "\n".join(linhas)


def _substituir_linhas(texto: str, trocas: dict[str, str]) -> str:
    """Reescreve o valor das chaves pedidas, no lugar onde elas ja estao.

    No LUGAR, e nao acrescentando no fim, porque duas linhas com a mesma
    variavel nao dao erro nenhum: o dotenv fica com a ultima e o arquivo passa
    a mentir para quem le. Linha comentada e ignorada -- se o valor esta
    desativado, quem escolheu isso foi o desenvolvedor.
    """
    saida = []
    for linha in texto.splitlines():
        despida = linha.strip()
        if despida and not despida.startswith("#") and "=" in despida:
            nome = despida.split("=", 1)[0].strip()
            if nome in trocas:
                saida.append(f"{nome}={trocas[nome]}")
                continue
        saida.append(linha)
    return "\n".join(saida) + ("\n" if texto.endswith("\n") else "")


def aplicar_env(plano: PlanoDoEnv) -> None:
    """Reescreve o que mudou de valor e acrescenta o que falta."""
    if not plano.tem_o_que_fazer:
        return

    if plano.substituindo and plano.caminho.is_file():
        texto = plano.caminho.read_text(encoding="utf-8")
        trocas = {chave.nome: chave.valor for chave, _ in plano.substituindo}
        plano.caminho.write_text(
            _substituir_linhas(texto, trocas), encoding="utf-8"
        )

    if not plano.faltando:
        return
    conteudo = _render_env(plano.faltando)
    if not plano.caminho.is_file():
        conteudo = "# Configuracao do agente. Gerado pelo /config.\n" + conteudo
    # restrito: o .env guarda credencial, igual ao ~/.aws/credentials.
    _acrescentar(plano.caminho, conteudo, restrito=True)


# ---------------------------------------------------------------------------
# A variavel persistente do usuario (Windows)
# ---------------------------------------------------------------------------
# O .env so vale para quem roda a partir do diretorio do projeto. A variavel de
# usuario vale para QUALQUER processo daquele login -- inclusive a IDE, um
# script solto ou um notebook que importe as libs internas.
#
# Escopo "usuario" (HKCU\Environment), nunca "maquina" (HKLM): maquina exige
# admin e afeta todo mundo que usa o computador.


@dataclass
class PlanoDoAmbiente:
    nome: str
    valor: str
    suportado: bool
    atual: str | None = None

    @property
    def tem_o_que_fazer(self) -> bool:
        # Nunca sobrescreve: se ja existe valor, ele fica. Vale tanto para a
        # sentinela repetida quanto para uma chave de verdade que o
        # desenvolvedor tenha posto ali.
        return self.suportado and self.atual is None


def _ler_variavel_persistente(nome: str) -> str | None:
    """Le do ambiente PERSISTENTE do usuario, nao do processo atual.

    Sao coisas diferentes: `os.environ` ja tem a sentinela (o config.py poe no
    import), entao consultar o processo diria sempre "ja existe" e a variavel
    nunca seria gravada de verdade.
    """
    if os.name != "nt":
        return None
    import winreg  # import local: modulo so existe no Windows

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as chave:
            valor, _ = winreg.QueryValueEx(chave, nome)
            return str(valor)
    except FileNotFoundError:
        return None
    except OSError:
        return None


def planejar_ambiente() -> PlanoDoAmbiente:
    return PlanoDoAmbiente(
        nome="OPENAI_API_KEY",
        valor=OPENAI_SENTINEL,
        suportado=os.name == "nt",
        atual=_ler_variavel_persistente("OPENAI_API_KEY"),
    )


def aplicar_ambiente(plano: PlanoDoAmbiente) -> None:
    """Grava a variavel de usuario com `setx`.

    `setx` e nao winreg de escrita porque ele ja avisa o Windows da mudanca
    (broadcast do WM_SETTINGCHANGE); escrevendo direto no registro, programas
    ja abertos nunca enxergariam a variavel nova.

    Vale lembrar do limite do setx: 1024 caracteres, truncando em silencio
    acima disso. Para a sentinela nao e problema, mas nao reaproveite esta
    funcao para segredo longo sem checar.
    """
    if not plano.tem_o_que_fazer:
        return
    subprocess.run(
        ["setx", plano.nome, plano.valor],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    # O setx so alcanca processos NOVOS. Sem isto, a sessao que acabou de
    # rodar o /config seguiria sem a variavel.
    os.environ[plano.nome] = plano.valor


# ---------------------------------------------------------------------------
# Os perfis da AWS
# ---------------------------------------------------------------------------

@dataclass
class PlanoDaAws:
    caminho_config: Path
    caminho_credentials: Path
    metodo: str = "sso"
    faltando: list[tuple[str, str]] = field(default_factory=list)  # (ambiente, perfil)
    ja_configurados: list[str] = field(default_factory=list)

    @property
    def tem_o_que_fazer(self) -> bool:
        return bool(self.faltando)

    @property
    def usa_credentials(self) -> bool:
        """So chave estatica mora no credentials. SSO nao poe nada la."""
        return self.metodo == "chave"


def caminho_do_aws_config() -> Path:
    """Onde a AWS CLI le a configuracao. Respeita AWS_CONFIG_FILE."""
    definido = os.getenv("AWS_CONFIG_FILE")
    if definido:
        return Path(definido).expanduser()
    return Path.home() / ".aws" / "config"


def caminho_do_aws_credentials() -> Path:
    """Onde ficam as chaves estaticas. Respeita AWS_SHARED_CREDENTIALS_FILE."""
    definido = os.getenv("AWS_SHARED_CREDENTIALS_FILE")
    if definido:
        return Path(definido).expanduser()
    return Path.home() / ".aws" / "credentials"


def _secoes(texto: str) -> set[str]:
    """Nomes das secoes `[...]` de um arquivo, cru, sem interpretar."""
    nomes = set()
    for linha in texto.splitlines():
        limpa = linha.strip()
        if limpa.startswith("[") and limpa.endswith("]"):
            nomes.add(limpa[1:-1].strip())
    return nomes


def _ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8") if caminho.is_file() else ""


def perfis_declarados() -> set[str]:
    """Perfis que a AWS CLI enxerga -- a UNIAO dos dois arquivos.

    Os dois arquivos nomeiam a mesma coisa de jeitos diferentes: no config a
    secao e `[profile NOME]`, no credentials e so `[NOME]`. E um perfil
    declarado apenas no credentials existe e funciona.

    Olhar so um dos dois faz o /config concluir que um perfil falta quando ele
    ja esta la, e criar um duplicado. E a mesma armadilha que o `aws.py`
    descreve em `perfis_configurados()` -- a diferenca e que la a resposta vem
    da propria CLI, e aqui precisamos ler os arquivos (a CLI pode nem estar
    instalada quando alguem roda o /config pela primeira vez).
    """
    nomes = set()
    for secao in _secoes(_ler(caminho_do_aws_config())):
        if secao == "default":
            nomes.add("default")
        elif secao.startswith("profile "):
            nomes.add(secao[len("profile ") :].strip())
    # No credentials a secao ja E o nome do perfil.
    nomes |= _secoes(_ler(caminho_do_aws_credentials()))
    return nomes


def planejar_aws(ambientes: list[str], metodo: str = "sso") -> PlanoDaAws:
    existentes = perfis_declarados()
    plano = PlanoDaAws(
        caminho_config=caminho_do_aws_config(),
        caminho_credentials=caminho_do_aws_credentials(),
        metodo=metodo,
    )
    for ambiente in ambientes:
        perfil = PERFIS[ambiente]
        if perfil in existentes:
            plano.ja_configurados.append(perfil)
        else:
            plano.faltando.append((ambiente, perfil))
    return plano


def bloco_de_perfil(ambiente: str, perfil: str, metodo: str) -> str:
    """O esqueleto de um perfil no ~/.aws/config.

    `region` e `output` ja vao preenchidos porque sao os mesmos para a area
    toda. O resto entra COMENTADO: sao valores que so o desenvolvedor tem, e
    um valor falso ativo daria erro de autenticacao em vez de erro de
    configuracao -- que e bem mais dificil de diagnosticar.
    """
    cabecalho = (
        f"\n# --- {ambiente} -- esqueleto criado pelo /config; "
        f"preencha e descomente ---\n"
        f"[profile {perfil}]\n"
        f"region = {REGIAO_PADRAO}\n"
        "output = json\n"
    )
    if metodo == "chave":
        return cabecalho + (
            f"# As chaves ficam no ~/.aws/credentials, na secao [{perfil}].\n"
        )
    return cabecalho + (
        "# Complete as quatro linhas abaixo e depois rode:\n"
        f"#     aws sso login --profile {perfil}\n"
        "# sso_start_url = https://SUA-ORG.awsapps.com/start\n"
        "# sso_region = us-east-1\n"
        "# sso_account_id = 000000000000\n"
        "# sso_role_name = SEU-ROLE\n"
    )


def bloco_de_credencial(ambiente: str, perfil: str) -> str:
    """O esqueleto de uma chave estatica no ~/.aws/credentials.

    Tudo comentado, pelo mesmo motivo da chave no .env: uma chave falsa ATIVA
    passaria pela deteccao e falharia so na chamada, como erro de autenticacao.
    Comentada, o perfil existe mas nao autentica -- e a AWS CLI diz "unable to
    locate credentials", que aponta para ca.
    """
    return (
        f"\n# --- {ambiente} -- esqueleto criado pelo /config; "
        f"preencha e descomente ---\n"
        f"[{perfil}]\n"
        "# aws_access_key_id = AKIA...\n"
        "# aws_secret_access_key = PREENCHA\n"
        "# Se a area exige MFA, a sessao temporaria tambem precisa desta:\n"
        "# aws_session_token = PREENCHA\n"
    )


def aplicar_aws(plano: PlanoDaAws) -> None:
    """Acrescenta os perfis que faltam. Nunca mexe no que ja existe."""
    if not plano.tem_o_que_fazer:
        return

    _acrescentar(
        plano.caminho_config,
        "".join(bloco_de_perfil(a, p, plano.metodo) for a, p in plano.faltando),
    )

    if plano.usa_credentials:
        _acrescentar(
            plano.caminho_credentials,
            "".join(bloco_de_credencial(a, p) for a, p in plano.faltando),
            restrito=True,
        )


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _acrescentar(caminho: Path, conteudo: str, restrito: bool = False) -> None:
    """Acrescenta no fim do arquivo, com backup se ele ja existia.

    `restrito` pede permissao 0600 ao CRIAR -- vale para o .env e para o
    ~/.aws/credentials, que guardam segredo em texto puro. So tem efeito em
    sistema POSIX; no Windows o controle e por ACL e o chmod nao faz nada,
    entao nao insistimos nem fingimos que protegeu.
    """
    if caminho.is_file():
        _fazer_backup(caminho)
        atual = caminho.read_text(encoding="utf-8")
        if atual and not atual.endswith("\n"):
            atual += "\n"
        novo_arquivo = False
    else:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        atual = ""
        novo_arquivo = True

    caminho.write_text(atual + conteudo, encoding="utf-8")

    if novo_arquivo and restrito:
        try:
            caminho.chmod(0o600)
        except OSError:
            pass  # sistema de arquivos sem suporte: segue o baile


def _agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _fazer_backup(caminho: Path) -> Path:
    """Copia o arquivo antes de mexer. Devolve o caminho da copia."""
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = caminho.with_name(f"{caminho.name}.bak-{carimbo}")
    shutil.copy2(caminho, destino)
    return destino
