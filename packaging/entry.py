"""Ponto de entrada unico do HUBMonitor.exe.

    HUBMonitor.exe ui [--tray-only]      janela + bandeja
    HUBMonitor.exe agent [argumentos]    nucleo do computador monitorado
    HUBMonitor.exe server [argumentos]   nucleo do servidor da loja
    HUBMonitor.exe export-connection     gera o arquivo .hubconn
    HUBMonitor.exe version
"""

from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path

VERSION = "1.0.0"

if not getattr(sys, "frozen", False):
    # Execucao a partir do codigo-fonte: garante que agent/server/desktop
    # sejam importaveis mesmo rodando "python packaging/entry.py".
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _dispatch(argv: list[str]) -> int:
    if not argv:
        argv = ["ui"]

    command, rest = argv[0].lower(), argv[1:]

    if command in ("version", "--version", "-v"):
        print(VERSION)
        return 0

    if command == "ui":
        from desktop.app import main as ui_main

        return ui_main(rest)

    if command == "agent":
        from agent.main import main as agent_main

        return agent_main(rest)

    if command == "server":
        from server.main import main as server_main

        return server_main(rest)

    if command in ("export-connection", "connection"):
        from server.services.connection_export import main as export_main

        return export_main(rest)

    print(f"Comando desconhecido: {command}", file=sys.stderr)
    print(__doc__, file=sys.stderr)
    return 2


def main() -> int:
    multiprocessing.freeze_support()
    return _dispatch(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
