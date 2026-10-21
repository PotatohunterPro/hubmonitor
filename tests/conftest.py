"""Fixtures compartilhadas da suite de testes."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest
from shared import constants as C  # noqa: E402
from shared.timeutil import to_iso, utc_now  # noqa: E402

_LAST_STATUS_TIME = utc_now()

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.config import ServerSettings  # noqa: E402
from server.database.db import Database  # noqa: E402


@pytest.fixture()
def settings(tmp_path, monkeypatch) -> ServerSettings:
    monkeypatch.setenv("DB_PATH", str(tmp_path / "bertolo.db"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("MIKROTIK_ENABLED", "false")
    monkeypatch.setenv("AGENT_INGEST_TOKEN", "test-agent-token")
    monkeypatch.setenv("SERVER_ALLOW_HTTP", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    monkeypatch.setenv("INCIDENT_FAILURE_THRESHOLD", "3")
    monkeypatch.setenv("INCIDENT_RECOVERY_THRESHOLD", "3")
    return ServerSettings.from_env()


@pytest.fixture()
def db(settings: ServerSettings) -> Database:
    database = Database(settings.db_path)
    yield database
    database.close()


def status(machine: str, **components) -> dict:
    """Monta um status de maquina com os componentes informados."""
    global _LAST_STATUS_TIME
    # A serializacao usa milissegundos. Garantimos um passo minimo entre
    # chamadas, senao duas observacoes no mesmo milissegundo viram a mesma
    # string e o motor as trata (corretamente) como duplicadas.
    current = utc_now()
    minimum = _LAST_STATUS_TIME + timedelta(milliseconds=50)
    if current < minimum:
        current = minimum
    _LAST_STATUS_TIME = current
    checked_at = to_iso(current)
    base = {
        "machine_name": machine,
        "online": True,
        "gateway_ok": True,
        "server_ok": True,
        "internet_ok": True,
        "dns_ok": True,
        "sefaz_tcp_ok": True,
        "sefaz_tls_ok": True,
        "tef_connected": True,
        "check_timestamps": {
            component: checked_at
            for component in (
                C.COMPONENT_GATEWAY,
                C.COMPONENT_SERVER,
                C.COMPONENT_INTERNET,
                C.COMPONENT_DNS,
                C.COMPONENT_SEFAZ_TCP,
                C.COMPONENT_SEFAZ_TLS,
            )
        },
    }
    base.update(components)
    return base
