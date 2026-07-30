"""Ponto de entrada da CLI do Custod.IA.

Uso:
    custodia [caminho-do-projeto] [--yes]

Sem argumento, usa a pasta atual. Abre um shell interativo onde o
desenvolvedor digita slash-commands:

    > /initialize    configura o projeto e salva a spec
    > /status        mostra a configuracao ja salva
    > /help          lista os comandos
    > /exit          sai

Com --yes, as ferramentas destrutivas (escrever arquivo, rodar maven) nao
param para pedir confirmacao. Use so quando voce ja sabe o que o agente vai
fazer -- ele ganha permissao de escrever no projeto sem perguntar.

Equivalente sem depender do executavel no PATH:
    python -m custodia [caminho-do-projeto]
"""

from __future__ import annotations

import sys

from .cli import repl
from .config import set_auto_approve, set_project_root
from .ui import configurar_saida_utf8


def main() -> int:
    configurar_saida_utf8()

    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    # A flag sai da lista antes de procurarmos o caminho: assim ela funciona
    # em qualquer posicao (`custodia --yes .` e `custodia . --yes`) sem que o
    # "--yes" acabe interpretado como nome de pasta.
    if "--yes" in args:
        set_auto_approve(True)
        args = [a for a in args if a != "--yes"]

    # Sem caminho, assume a pasta atual -- o fluxo normal e o dev entrar no
    # repositorio e rodar o comando ali.
    caminho = args[0] if args else "."

    try:
        raiz = set_project_root(caminho)
    except (NotADirectoryError, FileNotFoundError) as exc:
        print(f"ERRO: {exc}")
        return 1

    return repl(raiz)


if __name__ == "__main__":
    raise SystemExit(main())
