"""Ponto de entrada do bundle PyInstaller do servidor."""

from __future__ import annotations

import multiprocessing
import sys

from server.main import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
