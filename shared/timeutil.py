"""Utilitarios de tempo.

Regra do projeto (plano secao 23): tudo e persistido em UTC e apenas
renderizado em America/Sao_Paulo na borda (dashboard / Telegram).
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from shared.constants import TIMEZONE

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"


def utc_now() -> datetime:
    """Agora, sempre timezone-aware em UTC."""
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    """Normaliza um datetime (ingenuo ou nao) para UTC aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_iso(dt: datetime | None) -> str | None:
    """Serializa em ISO-8601 UTC com milissegundos e sufixo Z.

    O formato tem tamanho fixo, portanto a ordenacao lexicografica no
    SQLite coincide com a ordenacao cronologica.
    """
    if dt is None:
        return None
    dt = ensure_utc(dt)
    return dt.strftime(ISO_FORMAT)[:-3] + "Z"


def parse_iso(value: str | None) -> datetime | None:
    """Aceita ISO-8601 com ou sem Z, com ou sem milissegundos."""
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return ensure_utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def to_local(dt: datetime | None) -> datetime | None:
    """Converte para o fuso de operacao (America/Sao_Paulo)."""
    if dt is None:
        return None
    return ensure_utc(dt).astimezone(ZoneInfo(TIMEZONE))


def format_local(dt: datetime | str | None, fmt: str = "%d/%m/%Y %H:%M:%S") -> str:
    if isinstance(dt, str):
        dt = parse_iso(dt)
    local = to_local(dt)
    return local.strftime(fmt) if local else "-"


def format_duration(seconds: float | None) -> str:
    """Formata duracao no estilo usado no plano: 1m39s, 2h05m, 12s."""
    if seconds is None:
        return "-"
    seconds = int(max(0, seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"
