"""Permite rodar o agente sem depender do executavel no PATH:

    python -m custodia [caminho-do-projeto]
"""

from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
