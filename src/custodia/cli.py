"""O REPL: o shell interativo com slash-commands.

O desenvolvedor entra na pasta do repositorio, roda `springboot-agent` e cai
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

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from langgraph.types import Command

from .initialize import (
    STATUS_BLOQUEADO,
    STATUS_CANCELADO,
    STATUS_SALVO,
    build_initialize_graph,
    resumo_da_configuracao,
)
from .questions import Q_DEPENDENCIAS
from .spec import SpecError, load_spec, spec_path
from .ui import LARGURA, WizardAbortado, perguntar_no_terminal, titulo

VERSAO = "0.2.0"
NOME_AGENTE = f"springboot-agent {VERSAO}"


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
    print("\nComandos disponiveis:\n")
    for comando in _COMANDOS_UNICOS:
        apelidos = f"  (ou {', '.join(comando.apelidos)})" if comando.apelidos else ""
        print(f"  {comando.nome:<14} {comando.descricao}{apelidos}")
    print()
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
    return True


def cmd_status(root: Path) -> bool:
    """Mostra a spec ja salva no projeto, se houver."""
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


def cmd_exit(root: Path) -> bool:
    """Encerra o agente."""
    print("Ate mais.")
    return False


_COMANDOS_UNICOS: tuple[Comando, ...] = (
    Comando("/help", "Mostra esta ajuda.", cmd_help, apelidos=("/?",)),
    Comando(
        "/initialize",
        "Configura o projeto (worker SQS) e salva a spec.",
        cmd_initialize,
        apelidos=("/init",),
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
    print()
    print("=" * LARGURA)
    print(f"  Spring Boot Agent {VERSAO}")
    print(f"  Projeto: {root}")
    print("=" * LARGURA)
    print("Digite /help para ver os comandos, /exit para sair.")


def repl(root: Path) -> int:
    """Le comandos ate o usuario sair. Devolve o codigo de saida do processo."""
    _banner(root)

    while True:
        try:
            # lstrip do BOM (U+FEFF): no Windows, alimentar a CLI por pipe
            # (CI, scripts do PowerShell) costuma colar um BOM na primeira
            # linha; sem isso o primeiro comando seria rejeitado em silencio.
            entrada = input("\n> ").lstrip("\ufeff").strip()
        except EOFError:
            # Fim da entrada (Ctrl+D, ou stdin de um arquivo/pipe que acabou).
            print()
            return 0
        except KeyboardInterrupt:
            # Ctrl+C no prompt nao mata a sessao: so limpa a linha.
            print("\n(use /exit para sair)")
            continue

        if not entrada:
            continue

        if not entrada.startswith("/"):
            print(
                "Este agente responde a slash-commands. "
                "Digite /help para ver a lista."
            )
            continue

        # Ignora argumentos extras por enquanto: os comandos atuais nao usam.
        nome = entrada.split()[0].lower()
        comando = COMANDOS.get(nome)
        if comando is None:
            print(f"Comando desconhecido: {nome}. Digite /help.")
            continue

        if not comando.executar(root):
            return 0
