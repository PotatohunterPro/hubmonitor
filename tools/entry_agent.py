"""Ponto de entrada do bundle PyInstaller do agente."""

from __future__ import annotations

import multiprocessing
import sys

from agent.main import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
