"""Monitor 7.4 - DNS da SEFAZ.

Consulta o resolvedor configurado no proprio PDV e, em paralelo, um
resolvedor externo. A comparacao dos dois separa falha de DNS local de
falha de DNS do provedor - exatamente o que o plano pede na secao 14.
"""

from __future__ import annotations

import asyncio
import logging
import time

import dns.asyncresolver
import dns.exception
import dns.resolver

from agent.config import AgentSettings
from agent.monitors.base import CheckResult, Monitor
from shared import constants as C


class DnsMonitor(Monitor):
    component = C.COMPONENT_DNS

    def __init__(self, settings: AgentSettings) -> None:
        super().__init__(
            settings.intervals[C.COMPONENT_DNS],
            logging.getLogger("agent.monitor.dns"),
        )
        self.settings = settings

    def _resolver(self, nameservers: list[str] | None) -> dns.asyncresolver.Resolver:
        resolver = dns.asyncresolver.Resolver(configure=nameservers is None)
        if nameservers:
            resolver.nameservers = list(nameservers)
        resolver.lifetime = max(2.0, self.settings.tcp_timeout)
        resolver.timeout = max(1.0, self.settings.tcp_timeout / 2)
        return resolver

    async def _resolve(self, nameservers: list[str] | None) -> tuple[bool, float | None, list[str], str | None, list[str]]:
        try:
            resolver = self._resolver(nameservers)
        except Exception as exc:  # noqa: BLE001
            return False, None, [], f"resolvedor indisponivel: {exc}", []

        used = list(resolver.nameservers or [])
        started = time.perf_counter()
        try:
            answer = await resolver.resolve(self.settings.sefaz_host, "A")
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer) as exc:
            return False, None, [], f"sem resposta A: {type(exc).__name__}", used
        except dns.exception.Timeout:
            return False, None, [], "timeout na resolucao", used
        except dns.resolver.NoNameservers as exc:
            return False, None, [], f"nenhum nameserver respondeu: {exc}", used
        except Exception as exc:  # noqa: BLE001
            return False, None, [], f"{type(exc).__name__}: {exc}", used

        latency = round((time.perf_counter() - started) * 1000.0, 1)
        ips = sorted({rdata.address for rdata in answer})
        return True, latency, ips, None, used

    async def check(self) -> CheckResult:
        system_task = self._resolve(None)
        external_task = self._resolve(self.settings.external_dns_servers)
        system, external = await asyncio.gather(system_task, external_task)

        system_ok, system_latency, system_ips, system_error, system_servers = system
        external_ok, _, _, external_error, _ = external

        ok = system_ok
        error = system_error
        if not ok and external_ok:
            error = f"resolvedor local falhou ({system_error}); DNS externo respondeu"

        return CheckResult(
            component=self.component,
            ok=ok,
            latency_ms=system_latency,
            error=error,
            details={
                "host": self.settings.sefaz_host,
                "resolved_ips": system_ips,
                "resolver": ", ".join(system_servers) if system_servers else "sistema",
                "system_ok": system_ok,
                "system_error": system_error,
                "external_ok": external_ok,
                "external_error": external_error,
            },
        )
