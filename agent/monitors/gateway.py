"""Monitor 7.1 - Rede local / gateway (MikroTik)."""

from __future__ import annotations

import logging

from agent.config import AgentSettings
from agent.monitors.base import CheckResult, Monitor
from agent.netprobe import ping_once
from shared import constants as C


class GatewayMonitor(Monitor):
    component = C.COMPONENT_GATEWAY

    def __init__(self, settings: AgentSettings) -> None:
        super().__init__(
            settings.intervals[C.COMPONENT_GATEWAY],
            logging.getLogger("agent.monitor.gateway"),
        )
        self.settings = settings

    async def check(self) -> CheckResult:
        result = await ping_once(self.settings.gateway_ip, self.settings.ping_timeout_ms)
        return CheckResult(
            component=self.component,
            ok=result.ok,
            latency_ms=result.latency_ms,
            error=result.error,
            details={
                "host": result.host,
                "loss_pct": result.loss_pct,
                "target": "gateway",
            },
        )
