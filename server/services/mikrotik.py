"""Integração opcional com a MikroTik via API RouterOS, somente leitura.

Regras de seguranca:
  - o usuario configurado deve ser SOMENTE LEITURA, com policy
    read,api,test e sem write/policy/sensitive;
  - o acesso deve ser restrito ao IP 192.168.0.110 na propria RB;
  - nenhuma alteracao de configuracao e feita por este modulo.

O modulo e defensivo: se a RB estiver inacessivel ou algum menu nao
existir naquela versao do RouterOS, o servidor continua funcionando com
as WANs marcadas como desconhecidas.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence

from server.config import ServerSettings
from shared import constants as C
from shared.timeutil import utc_now

try:  # pragma: no cover - depende do pacote opcional
    import librouteros
except ImportError:  # pragma: no cover
    librouteros = None  # type: ignore[assignment]


@dataclass(slots=True)
class WanReading:
    wan_name: str
    provider: str
    status: str = "unknown"
    probe: str | None = None
    latency_ms: float | None = None
    active_route: bool | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "wan_name": self.wan_name,
            "provider": self.provider,
            "status": self.status,
            "probe": self.probe,
            "latency_ms": self.latency_ms,
            "active_route": self.active_route,
        }


@dataclass(slots=True)
class MikrotikSnapshot:
    ok: bool = False
    error: str | None = None
    checked_at: datetime = field(default_factory=utc_now)
    wans: list[WanReading] = field(default_factory=list)
    active_wan: str | None = None
    active_gateway: str | None = None
    active_interface: str | None = None
    netwatch_entries: int = 0
    route_count: int = 0


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "yes", "sim", "1"}


def _text(value: Any) -> str:
    return "" if value is None else str(value)


class MikrotikService:
    """Consulta periódica dos links na MikroTik da loja."""

    def __init__(self, settings: ServerSettings, logger: logging.Logger | None = None) -> None:
        self.settings = settings
        self.log = logger or logging.getLogger("server.mikrotik")
        self.last: MikrotikSnapshot | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.mikrotik_enabled and librouteros is not None)

    # ------------------------------------------------------------------
    async def poll(self) -> MikrotikSnapshot:
        if librouteros is None:
            return MikrotikSnapshot(ok=False, error="biblioteca librouteros nao instalada")
        if not self.settings.mikrotik_enabled:
            return MikrotikSnapshot(ok=False, error="integracao com a MikroTik desabilitada")
        snapshot = await asyncio.to_thread(self._poll_sync)
        self.last = snapshot
        return snapshot

    # ------------------------------------------------------------------
    def _poll_sync(self) -> MikrotikSnapshot:
        settings = self.settings
        try:
            api = librouteros.connect(
                host=settings.mikrotik_host,
                username=settings.mikrotik_user,
                password=settings.mikrotik_password,
                port=settings.mikrotik_port,
                timeout=8,
                ssl=settings.mikrotik_use_ssl,
            )
        except Exception as exc:  # noqa: BLE001
            self.log.warning("MikroTik inacessivel em %s: %s", settings.mikrotik_host, exc)
            return MikrotikSnapshot(ok=False, error=f"{type(exc).__name__}: {exc}")

        netwatch: list[dict[str, Any]] = []
        routes: list[dict[str, Any]] = []
        try:
            netwatch = self._read(api, "tool", "netwatch")
            routes = self._read(api, "ip", "route")
        finally:
            try:
                api.close()
            except Exception:  # noqa: BLE001
                pass

        snapshot = MikrotikSnapshot(ok=True, netwatch_entries=len(netwatch), route_count=len(routes))
        self._fill_wans(snapshot, netwatch)
        self._fill_active_route(snapshot, routes)
        return snapshot

    def _read(self, api: Any, *path: str) -> list[dict[str, Any]]:
        try:
            return [dict(item) for item in api.path(*path)]
        except Exception as exc:  # noqa: BLE001
            self.log.debug("Menu %s indisponivel: %s", "/".join(path), exc)
            return []

    # ------------------------------------------------------------------
    def _fill_wans(self, snapshot: MikrotikSnapshot, netwatch: Sequence[dict[str, Any]]) -> None:
        by_provider: dict[str, dict[str, Any]] = {}
        for entry in netwatch:
            haystack = f"{_text(entry.get('comment'))} {_text(entry.get('name'))} {_text(entry.get('host'))}"
            by_provider.setdefault(haystack.upper(), entry)

        for slot in C.WAN_SLOTS:
            provider = self.settings.wan_provider(slot)
            match = None
            reading = WanReading(wan_name=slot, provider=provider)
            # An empty mapping must remain unknown; the empty string would
            # otherwise match every Netwatch entry.
            if provider.strip():
                for haystack, entry in by_provider.items():
                    if provider.upper() in haystack:
                        match = entry
                        break
            if match is not None:
                status = _text(match.get("status")).lower()
                reading.status = "up" if status == "up" else ("down" if status == "down" else "unknown")
                reading.probe = _text(match.get("host")) or None
                for key in ("delay", "latency", "rtt"):
                    if match.get(key) is not None:
                        try:
                            reading.latency_ms = float(match[key])
                        except (TypeError, ValueError):
                            pass
                        break
            snapshot.wans.append(reading)

    def _fill_active_route(self, snapshot: MikrotikSnapshot, routes: Sequence[dict[str, Any]]) -> None:
        active_routes = []
        for route in routes:
            dst = _text(route.get("dst-address"))
            if dst in {"0.0.0.0/0", "0.0.0.0"} and _truthy(route.get("active")):
                active_routes.append(route)

        # ECMP ou rotas default ativas concorrentes nao identificam uma unica WAN.
        if len(active_routes) != 1:
            return
        active = active_routes[0]

        snapshot.active_gateway = _text(active.get("gateway")) or None
        snapshot.active_interface = (
            _text(active.get("interface")) or _text(active.get("pref-src")) or None
        )

        gateway = _gateway_key(snapshot.active_gateway)
        matches: list[str] = []
        if gateway:
            for slot in C.WAN_SLOTS:
                provider = self.settings.wan_provider(slot).upper()
                configured = (
                    self.settings.mikrotik_wan_gateways.get(provider)
                    or self.settings.mikrotik_wan_gateways.get(slot)
                    or ""
                )
                if configured and _gateway_key(configured) == gateway:
                    matches.append(slot)

        if len(matches) == 1:
            snapshot.active_wan = matches[0]
            for wan in snapshot.wans:
                wan.active_route = wan.wan_name == snapshot.active_wan
    # ------------------------------------------------------------------
    def status_payload(self) -> dict[str, Any]:
        snapshot = self.last
        if snapshot is None:
            return {"ok": None, "error": "nunca consultado", "wans": []}
        return {
            "ok": snapshot.ok,
            "error": snapshot.error,
            "checked_at": snapshot.checked_at.isoformat(),
            "active_wan": snapshot.active_wan,
            "active_gateway": snapshot.active_gateway,
            "active_interface": snapshot.active_interface,
            "netwatch_entries": snapshot.netwatch_entries,
            "wans": [wan.as_dict() for wan in snapshot.wans],
        }


def _gateway_key(value: str | None) -> str:
    """Compara o IP do next-hop sem aceitar prefixos ou correspondencias parciais."""
    text = _text(value).strip()
    if not text or "," in text:
        return ""
    return text.split("%", 1)[0].strip()
