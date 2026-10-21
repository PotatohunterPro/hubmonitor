"""Monitor 7.7 - TEF.

Observa as conexoes TCP abertas pelo PDV. Nao le conteudo de sessao e
nao toca em nenhum dado de cartao: apenas metadados de conexao
(IP, porta, estado e momento).

Regras do plano:
  - nunca usar IP fixo como identificacao unica do TEF;
  - a porta 55845 e apenas um sinal inicial;
  - registrar IP/porta/estado/duracao/quantidade.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter

import psutil

from agent.config import AgentSettings
from agent.monitors.base import CheckResult, Monitor
from shared import constants as C


class TefMonitor(Monitor):
    component = C.COMPONENT_TEF

    def __init__(self, settings: AgentSettings) -> None:
        super().__init__(
            settings.intervals[C.COMPONENT_TEF],
            logging.getLogger("agent.monitor.tef"),
        )
        self.settings = settings
        self.learning_mode = settings.tef_learning_mode
        self._port_counter: Counter[int] = Counter()
        self._first_seen: dict[tuple[str, int], float] = {}
        self.current_connections: list[dict] = []
        self.permission_ok: bool | None = None

    def _collect(self) -> list[dict]:
        connections: list[dict] = []
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status != psutil.CONN_ESTABLISHED or not conn.raddr:
                continue
            remote_ip, remote_port = conn.raddr[0], conn.raddr[1]
            connections.append(
                {
                    "remote_ip": remote_ip,
                    "remote_port": remote_port,
                    "pid": conn.pid,
                    "status": conn.status,
                }
            )
        return connections

    async def check(self) -> CheckResult:
        try:
            connections = await asyncio.to_thread(self._collect)
            self.permission_ok = True
        except psutil.AccessDenied as exc:
            self.permission_ok = False
            return CheckResult(
                component=self.component,
                ok=None,
                error=f"sem privilegio para listar conexoes: {exc}",
                details={"permission_ok": False},
            )
        except Exception as exc:  # noqa: BLE001
            self.permission_ok = False
            return CheckResult(
                component=self.component,
                ok=None,
                error=f"{type(exc).__name__}: {exc}",
                details={"permission_ok": False},
            )

        watch_ports = set(self.settings.tef_watch_ports)
        now = time.time()

        if self.learning_mode:
            for conn in connections:
                self._port_counter[conn["remote_port"]] += 1

        tef = [conn for conn in connections if conn["remote_port"] in watch_ports]

        seen_now: set[tuple[str, int]] = set()
        for conn in tef:
            key = (conn["remote_ip"], conn["remote_port"])
            seen_now.add(key)
            self._first_seen.setdefault(key, now)
        for key in list(self._first_seen):
            if key not in seen_now:
                self._first_seen.pop(key, None)

        self.current_connections = tef
        primary = tef[0] if tef else None

        details: dict = {
            "permission_ok": True,
            "watch_ports": sorted(watch_ports),
            "connections": tef[: C.TEF_MAX_TRACKED_CONNECTIONS],
            "total_established": len(connections),
        }
        if self.learning_mode:
            details["learned_top_ports"] = self._port_counter.most_common(10)

        return CheckResult(
            component=self.component,
            ok=bool(tef),
            latency_ms=None,
            error=None if tef else "nenhuma conexao TEF observada",
            details=details,
        )
