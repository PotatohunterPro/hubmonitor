"""Monitor 7.2 - Comunicacao com o servidor Bertolo.

Combina ICMP (latencia/perda) com uma verificacao HTTP periodica do
endpoint /health. A verificacao HTTP e menos frequente para nao gerar
carga desnecessaria.
"""

from __future__ import annotations

import logging
import time

import httpx

from agent.config import AgentSettings
from agent.monitors.base import CheckResult, Monitor
from agent.netprobe import ping_once
from shared import constants as C


class ServerMonitor(Monitor):
    component = C.COMPONENT_SERVER

    def __init__(self, settings: AgentSettings, http: httpx.AsyncClient, http_every: int = 5) -> None:
        super().__init__(
            settings.intervals[C.COMPONENT_SERVER],
            logging.getLogger("agent.monitor.server"),
        )
        self.settings = settings
        self.http = http
        self.http_every = max(1, http_every)
        self._iteration = 0
        self._last_http: tuple[bool | None, float | None] = (None, None)

    async def _http_health(self) -> tuple[bool, float | None]:
        started = time.perf_counter()
        try:
            response = await self.http.get(self.settings.health_url, timeout=3.0)
            latency = round((time.perf_counter() - started) * 1000.0, 1)
            return response.status_code == 200, latency
        except Exception:  # noqa: BLE001 - qualquer erro significa API inacessivel
            return False, None

    async def check(self) -> CheckResult:
        ping = await ping_once(self.settings.server_ip, self.settings.ping_timeout_ms)

        self._iteration += 1
        if self._iteration == 1 or self._iteration % self.http_every == 0:
            self._last_http = await self._http_health()
        http_ok, http_latency = self._last_http

        ok = bool(ping.ok) and http_ok is not False
        error = ping.error
        if ok and http_ok is False:
            error = "ICMP ok, porem a API nao respondeu em /health"
        elif not ok and http_ok is False:
            error = error or "API inacessivel"

        return CheckResult(
            component=self.component,
            ok=ok,
            latency_ms=ping.latency_ms,
            error=error,
            details={
                "host": ping.host,
                "loss_pct": ping.loss_pct,
                "http_ok": http_ok,
                "http_latency_ms": http_latency,
                "url": self.settings.health_url,
            },
        )
