"""Monitor 7.3 - Internet geral.

Regra do plano: nunca declarar a Internet indisponivel por falha de um
unico destino. A Internet e considerada OK se ao menos um alvo responder.

ICMP bloqueado em redes corporativas e o falso positivo mais comum.
Quando todos os pings falham, o monitor confirma por TCP antes de
declarar falha: se a porta 443 ou 53 de algum alvo aceitar conexao, a
Internet esta funcionando e o detalhe registra "icmp_blocked".
"""

from __future__ import annotations

import asyncio
import logging

from agent.config import AgentSettings
from agent.monitors.base import CheckResult, Monitor
from agent.netprobe import ping_once
from agent.netprobe import tcp_connect
from shared import constants as C

#: Portas usadas para confirmar conectividade quando o ICMP nao responde.
FALLBACK_PORTS: tuple[int, ...] = (443, 53)


class InternetMonitor(Monitor):
    component = C.COMPONENT_INTERNET

    def __init__(self, settings: AgentSettings) -> None:
        super().__init__(
            settings.intervals[C.COMPONENT_INTERNET],
            logging.getLogger("agent.monitor.internet"),
        )
        self.settings = settings

    async def _tcp_fallback(self, targets: list[str]) -> dict | None:
        for target in targets:
            for port in FALLBACK_PORTS:
                ok, latency, remote_ip, error = await tcp_connect(
                    target, port, timeout=max(1.0, self.settings.tcp_timeout / 2)
                )
                if ok:
                    return {
                        "host": target,
                        "port": port,
                        "latency_ms": latency,
                        "remote_ip": remote_ip,
                    }
                del error
        return None

    async def check(self) -> CheckResult:
        targets = self.settings.internet_targets
        results = await asyncio.gather(
            *(ping_once(target, self.settings.ping_timeout_ms) for target in targets)
        )
        reachable = [r for r in results if r.ok]
        icmp_ok = len(reachable) > 0

        fallback: dict | None = None
        if not icmp_ok:
            # Antes de alarmar, tenta provar conectividade sem ICMP.
            fallback = await self._tcp_fallback(targets)

        ok = icmp_ok or fallback is not None
        latencies = [r.latency_ms for r in reachable if r.latency_ms is not None]
        if icmp_ok:
            latency = min(latencies) if latencies else None
        else:
            latency = fallback.get("latency_ms") if fallback else None

        error = None
        if not ok:
            error = "; ".join(f"{r.host}: {r.error or 'falha'}" for r in results)

        return CheckResult(
            component=self.component,
            ok=ok,
            latency_ms=latency,
            error=error,
            details={
                "targets_ok": len(reachable),
                "targets_total": len(results),
                "icmp_blocked": (not icmp_ok) and ok,
                "tcp_fallback": fallback,
                "targets": [
                    {
                        "host": r.host,
                        "ok": r.ok,
                        "latency_ms": r.latency_ms,
                        "loss_pct": r.loss_pct,
                        "error": r.error,
                    }
                    for r in results
                ],
            },
        )
