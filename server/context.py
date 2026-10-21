"""Estado compartilhado do servidor (banco, servicos e cache de status)."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from server.config import ServerSettings
from server.database.db import Database
from server.services.diagnostics import machine_diagnosis
from server.services.incidents import IncidentManager
from server.services.mikrotik import MikrotikService, MikrotikSnapshot
from server.services.telegram import TelegramNotifier
from shared import constants as C
from shared.timeutil import format_local, parse_iso, utc_now

OFFLINE_AFTER_SECONDS = 60.0


@dataclass
class ServerContext:
    settings: ServerSettings
    db: Database
    http: httpx.AsyncClient
    mikrotik: MikrotikService
    notifier: TelegramNotifier
    incidents: IncidentManager
    started_at: float = field(default_factory=time.time)
    tasks: list[asyncio.Task] = field(default_factory=list)
    last_wan_snapshot: MikrotikSnapshot | None = None

    # ------------------------------------------------------------------
    def statuses(self) -> dict[str, dict[str, Any]]:
        """Ultimo estado conhecido de cada maquina, com diagnostico."""
        machines = {item["machine_name"]: item for item in self.db.list_machines()}
        latest = self.db.latest_measurements()
        now = utc_now()
        result: dict[str, dict[str, Any]] = {}

        for name, info in machines.items():
            measurement = latest.get(name, {})
            last_seen = parse_iso(info.get("last_seen"))
            age = (now - last_seen).total_seconds() if last_seen else None
            online = age is not None and age <= OFFLINE_AFTER_SECONDS

            status: dict[str, Any] = {
                "machine_name": name,
                "hostname": info.get("hostname") or name,
                "local_ip": info.get("local_ip") or "",
                "agent_version": info.get("agent_version") or "",
                "last_seen": last_seen,
                "seconds_since_last_seen": age,
                "online": online,
            }
            for component, column in (
                (C.COMPONENT_GATEWAY, "gateway_ok"),
                (C.COMPONENT_SERVER, "server_ok"),
                (C.COMPONENT_INTERNET, "internet_ok"),
                (C.COMPONENT_DNS, "dns_ok"),
                (C.COMPONENT_SEFAZ_TCP, "sefaz_tcp_ok"),
                (C.COMPONENT_SEFAZ_TLS, "sefaz_tls_ok"),
            ):
                status[column] = None if measurement.get(column) is None else bool(measurement[column])

            status["gateway_latency_ms"] = measurement.get("gateway_latency_ms")
            status["server_latency_ms"] = measurement.get("server_latency_ms")
            status["internet_latency_ms"] = measurement.get("internet_latency_ms")
            status["dns_latency_ms"] = measurement.get("dns_latency_ms")
            status["sefaz_tcp_latency_ms"] = measurement.get("sefaz_tcp_latency_ms")
            status["sefaz_tls_latency_ms"] = measurement.get("sefaz_tls_latency_ms")
            status["sefaz_cert_days_left"] = measurement.get("sefaz_cert_days_left")
            status["active_wan"] = measurement.get("active_wan")
            status["updated_at"] = measurement.get("timestamp")
            try:
                details = json.loads(measurement.get("details") or "{}")
            except (TypeError, ValueError):
                details = {}
            status["check_timestamps"] = {
                name: check.get("checked_at")
                for name, check in (details.get("checks") or {}).items()
                if isinstance(check, dict)
            }
            status["sefaz_authorization_log_configured"] = bool(
                (details.get("sefaz_authorization_log") or {}).get("configured")
            )

            if online:
                status["diagnosis"] = machine_diagnosis(status)
            else:
                status["diagnosis"] = C.DIAG_AGENT
            result[name] = status

        return result

    # ------------------------------------------------------------------
    def wan_statuses(self) -> list[dict[str, Any]]:
        rows = self.db.latest_wan_status()
        active = None
        for row in rows:
            if row.get("active_route"):
                active = row.get("wan_name")
                break
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "wan_name": row.get("wan_name"),
                    "provider": row.get("provider"),
                    "status": row.get("status") or "unknown",
                    "probe": row.get("probe"),
                    "latency_ms": row.get("latency_ms"),
                    "active_route": (
                        None if row.get("active_route") is None else bool(row.get("active_route"))
                    ),
                    "timestamp": row.get("timestamp"),
                }
            )
        self.active_wan = active
        return out

    active_wan: str | None = None

    # ------------------------------------------------------------------
    def active_wan_name(self) -> str | None:
        if self.active_wan:
            return self.active_wan
        for row in self.db.latest_wan_status():
            if row.get("active_route"):
                return row.get("wan_name")
        return "WAN desconhecida"

    def serialize_status(self) -> dict[str, Any]:
        statuses = self.statuses()
        for status in statuses.values():
            status["last_seen"] = _iso(status.get("last_seen"))
            status["updated_at"] = _iso(status.get("updated_at"))
            status["hostname"] = status.get("hostname") or ""
        wans = self.wan_statuses()
        incidents = self.db.list_incidents(limit=20)
        return {
            "store_name": self.settings.store_name,
            "title": self.settings.dashboard_title,
            "now_utc": _iso(utc_now()),
            "now_local": format_local(utc_now()),
            "retention_days": self.settings.retention_days,
            "machines": list(statuses.values()),
            "wans": wans,
            "active_wan": self.active_wan_name(),
            "incidents": incidents,
            "open_incidents": [item for item in incidents if item.get("open")],
            "mikrotik": self.mikrotik.status_payload(),
            "telegram_enabled": self.notifier.enabled,
        }


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    from shared.timeutil import to_iso

    return to_iso(value)
