"""Configuracao de logging do agente (arquivo rotativo + console)."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from shared.constants import LOG_BACKUP_COUNT, LOG_FORMAT, MAX_LOG_BYTES


def setup_logging(log_dir: Path, level: str = "INFO", filename: str = "agent.log") -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / filename

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=MAX_LOG_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # Reduz ruido de bibliotecas de terceiros
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    return log_path
