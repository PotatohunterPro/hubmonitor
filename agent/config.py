"""Configuracao do agente, carregada do .env e do ambiente.

Ordem de busca do .env:
  1. pasta do executavel/pacote (base_dir)
  2. pasta pai (raiz da instalacao)
  3. diretorio corrente
"""

from __future__ import annotations

import logging
import os
import platform
import socket
from typing import Any
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from shared import constants as C
from shared.connection_file import read_connection
from shared.constants import AGENT_VERSION


def app_base_dir() -> Path:
    """Diretorio base da aplicacao. Funciona tambem sob PyInstaller."""
    import sys

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def load_env() -> Path | None:
    """Carrega o primeiro .env encontrado, sem sobrescrever o ambiente."""
    base = app_base_dir()
    for candidate in (base / ".env", base.parent / ".env", Path.cwd() / ".env"):
        if candidate.is_file():
            # utf-8-sig tolera o BOM que o PowerShell 5.1 grava por padrao
            load_dotenv(candidate, override=False, encoding="utf-8-sig")
            return candidate
    return None


def _env(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(_env(name, str(default))))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name, "true" if default else "false").lower()
    return raw in {"1", "true", "yes", "y", "on", "sim"}


def _env_list(name: str, default: tuple[str, ...]) -> list[str]:
    raw = _env(name)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_int_list(name: str, default: tuple[int, ...]) -> list[int]:
    out: list[int] = []
    for item in _env_list(name, ()):
        try:
            out.append(int(item))
        except ValueError:
            continue
    return out or list(default)


def detect_local_ip(target: str = C.DEFAULT_SERVER_IP) -> str:
    """Descobre o IP local usado para alcancar o servidor.

    Nao envia pacote algum: apenas consulta a tabela de rotas do SO.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.5)
            sock.connect((target, 80))
            return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def detect_os_version() -> str:
    return f"{platform.system()} {platform.release()} ({platform.version()})"


def _resolve_dir(raw: str, fallback: Path) -> Path:
    if not raw:
        return fallback
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (app_base_dir() / path)


def _load_connection(base: Path) -> dict[str, Any]:
    """Le o arquivo de conexao da loja gravado pelo instalador.

    O instalador grava connection.json e extrai a CA publica para
    connection-ca.pem. Variaveis de ambiente continuam valendo quando
    nao houver arquivo (laboratorio).
    """
    raw = _env("CONNECTION_FILE")
    path = Path(raw).expanduser() if raw else base / "connection.json"
    if not path.is_file():
        return {}

    try:
        data = read_connection(path, allow_http=_env_bool("ALLOW_HTTP_CONNECTION", False))
    except Exception as exc:  # noqa: BLE001 - conexao invalida nao derruba o agente
        logging.getLogger("agent.config").error(
            "Arquivo de conexao invalido em %s: %s", path, exc
        )
        return {}

    ca_path = path.parent / (path.stem + "-ca.pem")
    try:
        ca_path.write_text(data["ca_certificate_pem"], encoding="utf-8")
        try:
            ca_path.chmod(0o600)
        except OSError:
            pass
    except OSError:
        ca_path = None

    return {
        "server_url": data["base_url"],
        "agent_token": data["agent_token"],
        "ca_file": ca_path,
        "connection_file": path,
        "fiscal": data.get("fiscal"),
    }


@dataclass(slots=True)
class AgentSettings:
    """Todas as configuracoes efetivas do agente."""

    machine_name: str
    store_name: str
    server_url: str
    server_ip: str
    server_ca_file: Path | None
    agent_ingest_token: str
    allow_insecure_http: bool
    gateway_ip: str
    sefaz_host: str
    sefaz_port: int
    fiscal_uf: str
    internet_targets: list[str]
    external_dns_servers: list[str]
    tef_watch_ports: list[int]
    tef_learning_mode: bool
    intervals: dict[str, float]
    snapshot_interval: float
    sender_interval: float
    queue_max_rows: int
    health_host: str
    health_port: int
    log_level: str
    tcp_timeout: float
    ping_timeout_ms: int
    agent_version: str
    base_dir: Path
    data_dir: Path
    log_dir: Path
    sefaz_authorization_log_path: Path | None
    env_file: Path | None = field(default=None)
    connection_file: Path | None = field(default=None)

    @property
    def queue_path(self) -> Path:
        return self.data_dir / "local_queue.db"

    @property
    def measurements_url(self) -> str:
        return self.server_url.rstrip("/") + "/api/v1/measurements"

    @property
    def events_url(self) -> str:
        return self.server_url.rstrip("/") + "/api/v1/events"

    @property
    def authorizations_url(self) -> str:
        return self.server_url.rstrip("/") + "/api/v1/sefaz-authorizations"

    @property
    def health_url(self) -> str:
        return self.server_url.rstrip("/") + "/health"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> AgentSettings:
        env_file = load_env()
        base = app_base_dir()
        connection = _load_connection(base)
        server_ip = _env("SERVER_IP", C.DEFAULT_SERVER_IP)

        # O destino fiscal da loja vem no arquivo de conexao; o .env local
        # continua valendo para laboratorio.
        fiscal = connection.get("fiscal") or {}
        sefaz_host = fiscal.get("host") or _env("SEFAZ_HOST", C.SEFAZ_HOST)
        sefaz_port = int(fiscal.get("port") or _env_int("SEFAZ_PORT", C.SEFAZ_PORT))
        fiscal_uf = fiscal.get("uf") or _env("FISCAL_UF")

        server_url = connection.get("server_url") or _env("SERVER_URL", C.DEFAULT_SERVER_URL)
        agent_token = connection.get("agent_token") or _env("AGENT_INGEST_TOKEN")
        if connection.get("ca_file") is not None:
            server_ca_file = connection["ca_file"]
        elif _env("SERVER_CA_FILE"):
            server_ca_file = _resolve_dir(_env("SERVER_CA_FILE"), base / "certs" / "server-ca.pem")
        else:
            server_ca_file = None

        intervals = {
            C.COMPONENT_GATEWAY: _env_float("INTERVAL_GATEWAY", C.DEFAULT_INTERVALS[C.COMPONENT_GATEWAY]),
            C.COMPONENT_SERVER: _env_float("INTERVAL_SERVER", C.DEFAULT_INTERVALS[C.COMPONENT_SERVER]),
            C.COMPONENT_INTERNET: _env_float(
                "INTERVAL_INTERNET", C.DEFAULT_INTERVALS[C.COMPONENT_INTERNET]
            ),
            C.COMPONENT_DNS: _env_float("INTERVAL_DNS", C.DEFAULT_INTERVALS[C.COMPONENT_DNS]),
            C.COMPONENT_SEFAZ_TCP: _env_float(
                "INTERVAL_SEFAZ_TCP", C.DEFAULT_INTERVALS[C.COMPONENT_SEFAZ_TCP]
            ),
            C.COMPONENT_SEFAZ_TLS: _env_float(
                "INTERVAL_SEFAZ_TLS", C.DEFAULT_INTERVALS[C.COMPONENT_SEFAZ_TLS]
            ),
            C.COMPONENT_TEF: _env_float("INTERVAL_TEF", C.DEFAULT_INTERVALS[C.COMPONENT_TEF]),
        }

        return cls(
            machine_name=_env("MACHINE_NAME", socket.gethostname()).upper(),
            store_name=_env("STORE_NAME", "LOJA MODELO"),
            server_url=server_url,
            server_ip=server_ip,
            server_ca_file=server_ca_file,
            agent_ingest_token=agent_token,
            allow_insecure_http=_env_bool("ALLOW_INSECURE_HTTP", False),
            gateway_ip=_env("GATEWAY_IP", C.DEFAULT_GATEWAY_IP),
            sefaz_host=sefaz_host,
            sefaz_port=sefaz_port,
            fiscal_uf=fiscal_uf,
            internet_targets=_env_list("INTERNET_TARGETS", C.INTERNET_TARGETS),
            external_dns_servers=_env_list("EXTERNAL_DNS_SERVERS", C.EXTERNAL_DNS_SERVERS),
            tef_watch_ports=_env_int_list("TEF_WATCH_PORTS", C.TEF_CANDIDATE_PORTS),
            tef_learning_mode=_env_bool("TEF_LEARNING_MODE", C.TEF_LEARNING_MODE),
            intervals=intervals,
            snapshot_interval=_env_float("SNAPSHOT_INTERVAL", C.SNAPSHOT_INTERVAL_SECONDS),
            sender_interval=_env_float("SENDER_INTERVAL", C.SENDER_INTERVAL_SECONDS),
            queue_max_rows=_env_int("QUEUE_MAX_ROWS", C.QUEUE_MAX_ROWS),
            health_host=_env("HEALTH_HOST", C.DEFAULT_HEALTH_HOST),
            health_port=_env_int("HEALTH_PORT", C.DEFAULT_HEALTH_PORT),
            log_level=_env("LOG_LEVEL", "INFO").upper(),
            tcp_timeout=_env_float("TCP_TIMEOUT", C.TCP_TIMEOUT_SECONDS),
            ping_timeout_ms=_env_int("PING_TIMEOUT_MS", C.PING_TIMEOUT_MS),
            agent_version=AGENT_VERSION,
            base_dir=base,
            data_dir=_resolve_dir(_env("DATA_DIR"), base / "data"),
            log_dir=_resolve_dir(_env("LOG_DIR"), base / "logs"),
            sefaz_authorization_log_path=(
                _resolve_dir(_env("SEFAZ_AUTHORIZATION_LOG_PATH"), base / "")
                if _env("SEFAZ_AUTHORIZATION_LOG_PATH")
                else None
            ),
            env_file=env_file,
            connection_file=connection.get("connection_file"),
        )
