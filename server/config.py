"""Configuracao do servidor central, carregada do .env."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from agent.config import app_base_dir, _env, _env_bool, _env_int, _env_list
from shared import constants as C


def load_env() -> Path | None:
    base = app_base_dir()
    for candidate in (base / ".env", base / "server" / ".env", Path.cwd() / ".env"):
        if candidate.is_file():
            # utf-8-sig tolera o BOM que o PowerShell 5.1 grava por padrao
            load_dotenv(candidate, override=False, encoding="utf-8-sig", interpolate=False)
            return candidate
    return None


def _resolve_dir(raw: str, fallback: Path) -> Path:
    if not raw:
        return fallback
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (app_base_dir() / path)


@dataclass(slots=True)
class ServerSettings:
    store_name: str
    host: str
    port: int
    agent_ingest_token: str
    allow_http: bool
    tls_cert_file: Path | None
    tls_key_file: Path | None
    local_subnet: str
    base_dir: Path
    data_dir: Path
    log_dir: Path
    db_path: Path
    dashboard_title: str
    retention_days: int
    incident_failure_threshold: int
    incident_recovery_threshold: int
    incident_aggregation_window: int
    telegram_enabled: bool
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_daily_summary: bool
    telegram_daily_summary_hour: int
    mikrotik_enabled: bool
    mikrotik_host: str
    mikrotik_port: int
    mikrotik_user: str
    mikrotik_password: str
    mikrotik_use_ssl: bool
    mikrotik_poll_interval: int
    mikrotik_wan_names: dict[str, str]
    mikrotik_wan_gateways: dict[str, str]
    log_level: str
    env_file: Path | None = None

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> ServerSettings:
        env_file = load_env()
        base = app_base_dir()

        wan_names = {
            "WAN1": _env("MIKROTIK_WAN1_NAME", C.WAN_MAP["WAN1"]).upper(),
            "WAN2": _env("MIKROTIK_WAN2_NAME", C.WAN_MAP["WAN2"]).upper(),
            "WAN3": _env("MIKROTIK_WAN3_NAME", C.WAN_MAP["WAN3"]).upper(),
        }
        wan_gateways: dict[str, str] = {}
        for item in _env_list("MIKROTIK_WAN_GATEWAYS", ()):
            if "=" in item:
                name, _, gateway = item.partition("=")
                wan_gateways[name.strip().upper()] = gateway.strip()

        token = _env("TELEGRAM_BOT_TOKEN")
        chat = _env("TELEGRAM_CHAT_ID")

        return cls(
            store_name=_env("STORE_NAME", "LOJA MODELO"),
            host=_env("SERVER_HOST", "0.0.0.0"),
            port=_env_int("SERVER_PORT", C.DEFAULT_SERVER_PORT),
            agent_ingest_token=_env("AGENT_INGEST_TOKEN"),
            allow_http=_env_bool("SERVER_ALLOW_HTTP", False),
            tls_cert_file=(
                _resolve_dir(_env("SERVER_TLS_CERT_FILE"), base / "server" / "certs" / "server.pem")
                if _env("SERVER_TLS_CERT_FILE")
                else None
            ),
            tls_key_file=(
                _resolve_dir(_env("SERVER_TLS_KEY_FILE"), base / "server" / "certs" / "server-key.pem")
                if _env("SERVER_TLS_KEY_FILE")
                else None
            ),
            local_subnet=_env("LOCAL_SUBNET", "192.168.0.0/24"),
            base_dir=base,
            data_dir=_resolve_dir(_env("DATA_DIR"), base / "server" / "data"),
            log_dir=_resolve_dir(_env("LOG_DIR"), base / "server" / "logs"),
            db_path=_resolve_dir(
                _env("DB_PATH"), base / "server" / "data" / "bertolo_monitor.db"
            ),
            dashboard_title=_env("DASHBOARD_TITLE", "HUB - SAÚDE OPERACIONAL DA LOJA"),
            retention_days=_env_int("RETENTION_DAYS", 90),
            incident_failure_threshold=_env_int(
                "INCIDENT_FAILURE_THRESHOLD", C.INCIDENT_FAILURE_THRESHOLD
            ),
            incident_recovery_threshold=_env_int(
                "INCIDENT_RECOVERY_THRESHOLD", C.INCIDENT_RECOVERY_THRESHOLD
            ),
            incident_aggregation_window=_env_int(
                "INCIDENT_AGGREGATION_WINDOW", C.INCIDENT_AGGREGATION_WINDOW_SECONDS
            ),
            telegram_enabled=bool(token and chat),
            telegram_bot_token=token,
            telegram_chat_id=chat,
            telegram_daily_summary=_env_bool("TELEGRAM_DAILY_SUMMARY", True),
            telegram_daily_summary_hour=_env_int("TELEGRAM_DAILY_SUMMARY_HOUR", 7),
            mikrotik_enabled=_env_bool("MIKROTIK_ENABLED", False),
            mikrotik_host=_env("MIKROTIK_HOST", C.DEFAULT_GATEWAY_IP),
            mikrotik_port=_env_int("MIKROTIK_PORT", 8728),
            mikrotik_user=_env("MIKROTIK_USER", "bertolo-monitor"),
            mikrotik_password=_env("MIKROTIK_PASSWORD"),
            mikrotik_use_ssl=_env_bool("MIKROTIK_USE_SSL", False),
            mikrotik_poll_interval=_env_int("MIKROTIK_POLL_INTERVAL", 15),
            mikrotik_wan_names=wan_names,
            mikrotik_wan_gateways=wan_gateways,
            log_level=_env("LOG_LEVEL", "INFO").upper(),
            env_file=env_file,
        )

    def wan_provider(self, slot: str) -> str:
        return self.mikrotik_wan_names.get(slot, slot)
