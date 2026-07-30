"""O REPL: o shell interativo com slash-commands.

O desenvolvedor entra na pasta do repositorio, roda `custodia` e cai
num prompt onde digita comandos:

    > /initialize
    > /status
    > /exit

Este arquivo tem duas responsabilidades:

1. O REGISTRO de comandos (`COMANDOS`). Acrescentar um comando novo e
   adicionar uma entrada aqui -- o loop nao muda.

2. DIRIGIR o grafo do wizard. Este e o padrao human-in-the-loop do LangGraph e
   vale entender bem:

       estado = grafo.invoke(entrada, config)     # roda ate pausar
       if estado["__interrupt__"]:                # pausou pedindo resposta
           resposta = perguntar_no_terminal(...)  # frontend responde
           entrada = Command(resume=resposta)     # retoma de onde parou
           # ... repete

   O `thread_id` no config identifica a conversa: e por ele que o checkpointer
   sabe qual estado restaurar ao retomar. Um `thread_id` novo por execucao do
   /initialize significa um wizard limpo a cada vez.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from langgraph.types import Command
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import NOME, __version__
from . import config
from . import iara
from .chat import ChatIndisponivel, Conversa, loop_de_conversa
from .configurar import (
    PLACEHOLDER,
    Q_AMBIENTES,
    Q_CONFIRMAR,
    Q_METODO_AWS,
    Q_PROVEDOR,
    aplicar_ambiente,
    aplicar_aws,
    aplicar_env,
    planejar_ambiente,
    planejar_aws,
    planejar_env,
)
from .conhecimento import esta_configurada
from .llm import descrever_llm
from .initialize import (
    STATUS_BLOQUEADO,
    STATUS_CANCELADO,
    STATUS_SALVO,
    build_initialize_graph,
    resumo_da_configuracao,
)
from .infra import (
    STATUS_BLOQUEADO as STATUS_BLOQUEADO_INFRA,
    STATUS_CANCELADO as STATUS_CANCELADO_INFRA,
    STATUS_ERRO_AWS,
    STATUS_ESCRITO,
    build_infra_graph,
)
from .questions import Q_DEPENDENCIAS
from .spec import SpecError, load_spec, spec_path
from .terraform import InfraNaoEncontrada, localizar_infra
from .ui import LARGURA, WizardAbortado, console, perguntar_no_terminal, titulo

VERSAO = __version__
# Assinatura gravada no campo `generated_by` da spec.
NOME_AGENTE = f"{NOME} {VERSAO}"

# Uma conversa por sessao. O /chat e o texto solto digitado no prompt principal
# falam com ESTA instancia -- ou seja, compartilham o mesmo historico.
_CONVERSA = Conversa()


def recarregar_configuracao() -> None:
    """Faz o processo inteiro enxergar o .env que o /config acabou de escrever.

    Sao tres camadas guardando decisoes tomadas na leitura anterior, e todas
    precisam largar o osso -- se uma ficar para tras, o agente passa a mentir
    sobre si mesmo: o /status diz um provedor e a conversa fala com outro.
    """
    config.recarregar()
    # O cliente do gateway ja esta autenticado no ambiente antigo.
    iara.esquecer_cliente()
    # E o grafo ja tem o modelo antigo amarrado nas ferramentas.
    _CONVERSA.esquecer_modelo()


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Comando:
    """Um slash-command.

    `executar` recebe a raiz do projeto e devolve True para continuar o REPL
    ou False para encerrar.
    """

    nome: str
    descricao: str
    executar: Callable[[Path], bool]
    apelidos: tuple[str, ...] = ()


def cmd_help(root: Path) -> bool:
    """Lista os comandos disponiveis."""
    tabela = Table(box=None, show_header=False, padding=(0, 2, 0, 0))
    tabela.add_column(style="bold")
    tabela.add_column()
    tabela.add_column(style="dim")

    tabela.add_row(
        "<texto>", "Conversa com o agente -- e so digitar, sem barra.", ""
    )
    for comando in _COMANDOS_UNICOS:
        apelidos = f"ou {', '.join(comando.apelidos)}" if comando.apelidos else ""
        tabela.add_row(comando.nome, comando.descricao, apelidos)

    console.print()
    console.print(tabela)
    console.print()
    return True


def cmd_initialize(root: Path) -> bool:
    """Roda o wizard deterministico e grava a spec."""
    titulo("/initialize - configuracao do projeto")

    grafo = build_initialize_graph()
    # thread_id novo => wizard do zero, sem herdar respostas de execucoes
    # anteriores nesta mesma sessao.
    config = {"configurable": {"thread_id": uuid4().hex}}

    entrada: Any = {"project_root": str(root), "agent_version": NOME_AGENTE}
    estado: dict[str, Any] = {}

    try:
        while True:
            estado = grafo.invoke(entrada, config=config)
            interrupcoes = estado.get("__interrupt__")
            if not interrupcoes:
                break  # o grafo chegou ao END
            # Cada pausa traz exatamente uma pergunta (um interrupt por no).
            resposta = perguntar_no_terminal(interrupcoes[0].value)
            entrada = Command(resume=resposta)
    except WizardAbortado:
        print("\n/initialize cancelado. Nada foi salvo.\n")
        return True

    _relatar_resultado(estado)
    _nota_de_fluxo_deterministico()
    return True


def cmd_config(root: Path) -> bool:
    """Cria o esqueleto do .env e dos perfis da AWS."""
    titulo("/config - prepara o ambiente do agente")

    try:
        provedor = perguntar_no_terminal(Q_PROVEDOR.to_dict())
        ambientes = perguntar_no_terminal(Q_AMBIENTES.to_dict())
        # So perguntamos o metodo se houver perfil a criar: quem nao marcou
        # ambiente nenhum nao precisa responder sobre autenticacao da AWS.
        metodo = (
            perguntar_no_terminal(Q_METODO_AWS.to_dict()) if ambientes else "sso"
        )
    except WizardAbortado:
        console.print("\n[yellow]/config cancelado. Nada foi escrito.[/yellow]\n")
        return True

    plano_env = planejar_env(provedor)
    plano_aws = planejar_aws(ambientes, metodo)
    plano_amb = planejar_ambiente()

    pendencias = (
        len(plano_env.faltando)
        + len(plano_env.substituindo)
        + len(plano_aws.faltando)
        + (1 if plano_amb.tem_o_que_fazer else 0)
    )
    _mostrar_plano(plano_env, plano_aws, plano_amb)

    if not pendencias:
        console.print("\n[green]Nada a fazer: ja esta tudo configurado.[/green]\n")
        _nota_de_fluxo_deterministico()
        return True

    try:
        if not perguntar_no_terminal(Q_CONFIRMAR(pendencias).to_dict()):
            console.print("\n[yellow]/config cancelado. Nada foi escrito.[/yellow]\n")
            return True
    except WizardAbortado:
        console.print("\n[yellow]/config cancelado. Nada foi escrito.[/yellow]\n")
        return True

    try:
        aplicar_env(plano_env)
        aplicar_aws(plano_aws)
        aplicar_ambiente(plano_amb)
    except OSError as exc:
        console.print(f"\n[red]Falha ao escrever:[/red] {escape(str(exc))}\n")
        return True
    except subprocess.CalledProcessError as exc:
        # Arquivos ja foram escritos; so a variavel de usuario falhou.
        console.print(
            f"\n[yellow]Arquivos gravados, mas o setx falhou:[/yellow] "
            f"{escape((exc.stderr or str(exc)).strip())}\n"
        )

    # O .env mudou -- releia AGORA. Sem isto o processo seguiria com o que foi
    # lido quando a CLI subiu: o /status anunciaria o provedor antigo e a
    # conversa continuaria falando com ele. Fica fora do try de proposito: o
    # arquivo ja esta escrito mesmo que o setx tenha falhado.
    recarregar_configuracao()

    _relatar_config(plano_env, plano_aws, plano_amb)
    console.print(f"[dim]LLM ativa agora:[/dim] {descrever_llm()}\n")
    _nota_de_fluxo_deterministico()
    return True


def _mostrar_plano(plano_env: Any, plano_aws: Any, plano_amb: Any) -> None:
    """Mostra exatamente o que vai ser escrito, antes de escrever."""
    console.print()
    console.print("[bold]variavel de usuario do Windows[/bold]")
    if not plano_amb.suportado:
        console.print(
            f"  [dim]- {plano_amb.nome}  (so no Windows; neste sistema use o "
            "seu ~/.profile)[/dim]"
        )
    elif plano_amb.atual is not None:
        console.print(f"  [dim]= {plano_amb.nome}  (ja definida, nao vou tocar)[/dim]")
    else:
        console.print(
            f"  [green]+[/green] {plano_amb.nome}={plano_amb.valor}  "
            "[dim](vale para qualquer processo seu, nao so o agente)[/dim]"
        )

    console.print()
    console.print(f"[bold]{escape(str(plano_env.caminho))}[/bold]")
    for nome in plano_env.ja_configuradas:
        console.print(f"  [dim]= {nome}  (ja existe, nao vou tocar)[/dim]")
    # A troca aparece com o valor VELHO junto: e a unica linha do plano que
    # apaga algo, entao quem confirma precisa ver o que vai perder.
    for chave, anterior in plano_env.substituindo:
        console.print(
            f"  [yellow]~[/yellow] {chave.nome}={chave.valor}  "
            f"[dim](era {anterior})[/dim]"
        )
    for chave in plano_env.faltando:
        prefixo = "# " if chave.comentada else ""
        console.print(f"  [green]+[/green] {prefixo}{chave.nome}={chave.valor}")

    console.print()
    console.print(f"[bold]{escape(str(plano_aws.caminho_config))}[/bold]")
    # escape() obrigatorio: "[profile X]" e sintaxe de markup do rich, e sem
    # escapar o nome do perfil some da tela em silencio.
    for perfil in plano_aws.ja_configurados:
        cabecalho = escape(f"[profile {perfil}]")
        console.print(f"  [dim]= {cabecalho}  (ja existe, nao vou tocar)[/dim]")
    for _, perfil in plano_aws.faltando:
        cabecalho = escape(f"[profile {perfil}]")
        console.print(f"  [green]+[/green] {cabecalho}  (esqueleto para preencher)")

    if plano_aws.usa_credentials:
        console.print()
        console.print(f"[bold]{escape(str(plano_aws.caminho_credentials))}[/bold]")
        for _, perfil in plano_aws.faltando:
            console.print(
                f"  [green]+[/green] {escape(f'[{perfil}]')}  "
                "(chave estatica, comentada)"
            )
    elif plano_aws.faltando:
        console.print(
            "\n[dim]~/.aws/credentials nao sera tocado: no SSO a credencial e "
            "temporaria e fica no cache do proprio aws-cli.[/dim]"
        )


def _relatar_config(plano_env: Any, plano_aws: Any, plano_amb: Any) -> None:
    """O que fazer agora. Sem isto o /config entrega arquivo pela metade."""
    console.print("\n[green]Esqueleto criado.[/green] Falta preencher:\n")

    passo = 1
    if plano_amb.tem_o_que_fazer:
        console.print(
            f"  {passo}. [bold]{plano_amb.nome}[/bold] foi gravada no seu perfil "
            "do Windows.\n"
            "       [dim]Ja vale nesta sessao, mas terminais e IDEs que ja "
            "estavam abertos\n       so enxergam depois de reabrir.[/dim]"
        )
        passo += 1
    if not plano_amb.suportado:
        console.print(
            f"  {passo}. Fora do Windows, ponha no seu ~/.profile (ou equivalente):\n"
            f"       [dim]export {plano_amb.nome}={plano_amb.valor}[/dim]"
        )
        passo += 1
    a_preencher = [c for c in plano_env.faltando if c.comentada and c.valor == PLACEHOLDER]
    if a_preencher:
        console.print(f"  {passo}. Em {escape(str(plano_env.caminho))}:")
        for chave in a_preencher:
            console.print(f"       descomente [bold]{chave.nome}[/bold] e ponha o valor")
        passo += 1

    if plano_aws.faltando and not plano_aws.usa_credentials:
        console.print(f"  {passo}. Em {escape(str(plano_aws.caminho_config))}:")
        for _, perfil in plano_aws.faltando:
            console.print(f"       complete o SSO de [bold]{perfil}[/bold], e entao:")
            # soft_wrap para o comando nao quebrar no meio: linha partida nao
            # se copia, e copiar isto e exatamente o que a pessoa vai fazer.
            console.print(
                f"         [dim]aws sso login --profile {perfil}[/dim]", soft_wrap=True
            )
        passo += 1
    elif plano_aws.faltando:
        console.print(f"  {passo}. Em {escape(str(plano_aws.caminho_credentials))}:")
        for _, perfil in plano_aws.faltando:
            console.print(
                f"       descomente a secao {escape(f'[{perfil}]')} e cole as chaves"
            )
        console.print(
            "       [dim]a chave estatica nao expira -- trate o arquivo como "
            "segredo e prefira SSO se a area permitir.[/dim]"
        )
        passo += 1

    console.print(
        f"\n  {passo}. Confira com [bold]/status[/bold] "
        "[dim](e /infra, que checa os perfis de verdade na AWS).[/dim]\n"
    )


def _nota_de_fluxo_deterministico() -> None:
    """Fecha um wizard dizendo que ele nao custou token nenhum.

    Nao e enfeite: os wizards (/initialize, /infra) sao grafos deterministicos
    -- perguntam, validam e escrevem arquivo, sem passar por modelo. Como a
    conversa mostra o gasto a cada volta, deixar o zero implicito aqui daria a
    impressao de que todo o agente cobra por uso.
    """
    console.print("[dim]  0 tokens -- fluxo deterministico, sem chamada ao modelo.[/dim]\n")


def cmd_infra(root: Path) -> bool:
    """Configura o terraform do worker, um ambiente por vez."""
    titulo("/infra - configuracao da infraestrutura")

    # Falhar aqui e melhor do que falhar depois de dezenas de perguntas.
    try:
        pasta = localizar_infra(root)
    except InfraNaoEncontrada as exc:
        console.print(f"\n[yellow]{escape(str(exc))}[/yellow]\n")
        return True
    console.print(f"[dim]infra encontrada em {escape(str(pasta))}[/dim]")

    # A vazao da spec entra so como sugestao no enunciado das perguntas.
    sugestao = None
    try:
        spec = load_spec(root)
    except SpecError:
        spec = None
    if spec is not None and spec.sqs is not None:
        sugestao = spec.sqs.messages_per_second

    grafo = build_infra_graph()
    config = {"configurable": {"thread_id": uuid4().hex}}
    entrada: Any = {"project_root": str(root), "sugestao_vazao": sugestao}
    estado: dict[str, Any] = {}

    try:
        while True:
            estado = grafo.invoke(entrada, config=config)
            interrupcoes = estado.get("__interrupt__")
            if not interrupcoes:
                break
            resposta = perguntar_no_terminal(interrupcoes[0].value)
            entrada = Command(resume=resposta)
    except WizardAbortado:
        console.print("\n[yellow]/infra cancelado. Nada foi escrito.[/yellow]\n")
        return True

    _relatar_infra(estado)
    _nota_de_fluxo_deterministico()
    return True


def _relatar_infra(estado: dict[str, Any]) -> None:
    status = estado.get("status")
    mensagem = estado.get("message", "")

    if status == STATUS_ESCRITO:
        escritos = estado.get("escritos", [])
        console.print(f"\n[green]Infra escrita.[/green] {len(escritos)} arquivo(s):\n")
        for caminho in escritos:
            console.print(f"  [dim]{escape(caminho)}[/dim]")
        console.print(
            "\n[dim]Proximo passo: revise o diff e rode o terraform "
            "com o profile do ambiente.[/dim]\n"
        )
        return

    if status == STATUS_ERRO_AWS:
        console.print(f"\n[red]{escape(mensagem)}[/red]\n")
        return

    if status in (STATUS_BLOQUEADO_INFRA, STATUS_CANCELADO_INFRA):
        console.print(f"\n[yellow]{escape(mensagem)}[/yellow]\n")
        return

    console.print("\n[yellow]O /infra terminou sem produzir um resultado.[/yellow]\n")


def cmd_status(root: Path) -> bool:
    """Mostra a spec ja salva no projeto, se houver."""
    # Antes da spec: quem vai responder e se a base de conhecimento esta ligada.
    # Configuracao de LLM e de KB e o que mais da problema silencioso na
    # primeira instalacao, entao aparece sem precisar abrir o .env.
    print(f"\nLLM                    : {descrever_llm()}")
    print(
        "Base de conhecimento   : "
        + (
            f"KB {config.KB_ID}"
            if esta_configurada()
            else "nao configurada (KB_ID vazio)"
        )
    )
    # O contador da sessao inteira. Enquanto so rodarem wizards ele fica em
    # zero -- e essa e a leitura util: o custo aparece so quando alguem
    # conversa, porque so a conversa chama o modelo.
    print(f"Tokens nesta sessao    : {_CONVERSA.uso_da_sessao.resumo()}")

    try:
        spec = load_spec(root)
    except SpecError as exc:
        print(f"\nERRO ao ler a spec: {exc}\n")
        return True

    if spec is None:
        print(
            f"\nNenhuma spec encontrada em {spec_path(root)}."
            "\nRode /initialize para configurar o projeto.\n"
        )
        return True

    labels = []
    for valor in spec.dependencies:
        opcao = Q_DEPENDENCIAS.option(valor)
        labels.append(opcao.label if opcao else valor)

    print(f"\nSpec atual ({spec_path(root)}):\n")
    print(f"  Tipo de projeto      : {spec.project_type}")
    print(f"  Gatilho              : {spec.trigger}")
    if spec.sqs:
        print(f"  Fila SQS             : {spec.sqs.queue_name}")
        print(f"  Mensagens por segundo: {spec.sqs.messages_per_second}")
    print(f"  Dependencias         : {', '.join(labels) or 'nenhuma'}")
    print(f"  Gerada em            : {spec.generated_at or '-'}")
    print(f"  Gerada por           : {spec.generated_by or '-'}\n")
    return True


def cmd_chat(root: Path) -> bool:
    """Abre o modo conversa com o agente."""
    try:
        loop_de_conversa(_CONVERSA)
    except ChatIndisponivel as exc:
        print(f"\nERRO: {exc}\n")
    return True


def cmd_exit(root: Path) -> bool:
    """Encerra o agente."""
    print("Ate mais.")
    return False


_COMANDOS_UNICOS: tuple[Comando, ...] = (
    Comando("/help", "Mostra esta ajuda.", cmd_help, apelidos=("/?",)),
    Comando(
        "/chat",
        "Conversa com o agente: duvidas ou alteracoes no codigo.",
        cmd_chat,
        apelidos=("/conversar",),
    ),
    Comando(
        "/config",
        "Cria o esqueleto do .env e dos perfis da AWS que o agente precisa.",
        cmd_config,
        apelidos=("/configurar",),
    ),
    Comando(
        "/initialize",
        "Configura o projeto (worker SQS) e salva a spec.",
        cmd_initialize,
        apelidos=("/init",),
    ),
    Comando(
        "/infra",
        "Configura o terraform do worker (dev/hom/prod) consultando a AWS.",
        cmd_infra,
    ),
    Comando("/status", "Mostra a configuracao ja salva neste projeto.", cmd_status),
    Comando("/exit", "Sai do agente.", cmd_exit, apelidos=("/quit",)),
)

# Mapa de busca: nome e apelidos apontam para o mesmo comando.
COMANDOS: dict[str, Comando] = {}
for _comando in _COMANDOS_UNICOS:
    COMANDOS[_comando.nome] = _comando
    for _apelido in _comando.apelidos:
        COMANDOS[_apelido] = _comando


# ---------------------------------------------------------------------------
# Relatorio final do /initialize
# ---------------------------------------------------------------------------

def _relatar_resultado(estado: dict[str, Any]) -> None:
    """Traduz o estado final do grafo numa mensagem para o desenvolvedor."""
    status = estado.get("status")
    mensagem = estado.get("message", "")

    if status == STATUS_SALVO:
        print("\n" + "-" * LARGURA)
        print("Configuracao salva.\n")
        print(resumo_da_configuracao(estado))
        print(f"\n  Arquivo: {estado.get('spec_path')}")
        print("-" * LARGURA)
        print(
            "\nProximo passo: commite a spec junto com o codigo. Os comandos de\n"
            "geracao (/generate, /infra) vao ler esse arquivo -- em breve.\n"
        )
        return

    if status == STATUS_BLOQUEADO:
        print(f"\n[FEATURE INDISPONIVEL] {mensagem}")
        print("Por enquanto o agente suporta apenas: worker com consumo SQS.\n")
        return

    if status == STATUS_CANCELADO:
        print(f"\n{mensagem}\n")
        return

    print("\nO wizard terminou sem produzir um resultado.\n")


# ---------------------------------------------------------------------------
# O loop do REPL
# ---------------------------------------------------------------------------

def _banner(root: Path) -> None:
    cabecalho = Text()
    cabecalho.append(f"{NOME} ", style="bold cyan")
    cabecalho.append(VERSAO, style="dim")
    cabecalho.append("\nAgente da custodia de ativos PF", style="white")
    cabecalho.append("\n\nProjeto  ", style="dim")
    cabecalho.append(str(root))

    console.print()
    console.print(Panel(cabecalho, border_style="cyan", padding=(1, 3), expand=False))
    console.print(
        "[dim]Pergunte qualquer coisa, ou digite[/dim] [bold]/help[/bold] "
        "[dim]para ver os comandos.[/dim]"
    )


def repl(root: Path) -> int:
    """Le comandos ate o usuario sair. Devolve o codigo de saida do processo."""
    _banner(root)

    while True:
        try:
            # lstrip do BOM (U+FEFF): no Windows, alimentar a CLI por pipe
            # (CI, scripts do PowerShell) costuma colar um BOM na primeira
            # linha; sem isso o primeiro comando seria rejeitado em silencio.
            entrada = console.input("\n[bold cyan]>[/bold cyan] ").lstrip("\ufeff").strip()
        except EOFError:
            # Fim da entrada (Ctrl+D, ou stdin de um arquivo/pipe que acabou).
            console.print()
            return 0
        except KeyboardInterrupt:
            # Ctrl+C no prompt nao mata a sessao: so limpa a linha.
            console.print("\n[dim](use /exit para sair)[/dim]")
            continue

        if not entrada:
            continue

        # Texto sem barra e conversa, como no Claude Code. As barras ficam
        # reservadas para os comandos deterministicos (/initialize, /status).
        if not entrada.startswith("/"):
            try:
                _CONVERSA.perguntar(entrada)
            except ChatIndisponivel as exc:
                console.print(f"\n[yellow]{escape(str(exc))}[/yellow]\n")
            continue

        # Ignora argumentos extras por enquanto: os comandos atuais nao usam.
        nome = entrada.split()[0].lower()
        comando = COMANDOS.get(nome)
        if comando is None:
            console.print(
                f"[yellow]Comando desconhecido:[/yellow] {escape(nome)}. "
                "Digite [bold]/help[/bold]."
            )
            continue

        if not comando.executar(root):
            return 0
