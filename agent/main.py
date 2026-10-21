"""Agente local do serviço HUB Monitoramento.

Uso:
    python -m agent.main              # executa continuamente (servico)
    python -m agent.main --once       # executa uma rodada e imprime JSON
    python -m agent.main --print-config
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
from typing import Any

import httpx

from agent.config import AgentSettings, detect_local_ip, detect_os_version
from agent.health import HealthServer
from agent.logging_setup import setup_logging
from agent.monitors.base import CheckResult, Monitor, Transition
from agent.monitors.dns_monitor import DnsMonitor
from agent.monitors.gateway import GatewayMonitor
from agent.monitors.internet import InternetMonitor
from agent.monitors.sefaz import SefazTcpMonitor, SefazTlsMonitor
from agent.monitors.server import ServerMonitor
from agent.queue.local_queue import LocalQueue
from agent.sender import Sender
from agent.sefaz_authorization_log import SefazAuthorizationLogReader
from agent.snapshot import build_measurement
from agent.tlsutil import build_ingest_ssl_context
from shared import constants as C
from shared.schemas import EventIn, MachineInfo
from shared.timeutil import to_iso, utc_now

DRAIN_TIMEOUT_SECONDS = 20.0


class Agent:
    """Orquestra monitores, fila local, sender e health."""

    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings
        if settings.server_url.lower().startswith("http://") and not settings.allow_insecure_http:
            raise ValueError("SERVER_URL precisa usar HTTPS (HTTP so e permitido em desenvolvimento explicito).")
        self.log = logging.getLogger("agent")
        self.stop_event = asyncio.Event()
        self.started_at = time.time()

        self.queue = LocalQueue(settings.queue_path, max_rows=settings.queue_max_rows)
        self.http = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            headers={
                "User-Agent": f"BertoloAgent/{settings.agent_version}",
                "Authorization": f"Bearer {settings.agent_ingest_token}",
            },
            verify=build_ingest_ssl_context(settings.server_ca_file),
        )
        self.machine = MachineInfo(
            machine_name=settings.machine_name,
            hostname=settings.machine_name,
            local_ip=detect_local_ip(settings.server_ip),
            agent_version=settings.agent_version,
            os_version=detect_os_version(),
            collected_at=utc_now(),
        )
        self.monitors: dict[str, Monitor] = {}
        self.authorization_log = (
            SefazAuthorizationLogReader(
                settings.sefaz_authorization_log_path,
                settings.machine_name,
                self.queue,
            )
            if settings.sefaz_authorization_log_path
            else None
        )
        self.sender = Sender(settings, self.queue, self.http, self.machine)
        self.health = HealthServer(
            settings.health_host,
            settings.health_port,
            self.health_payload,
            logging.getLogger("agent.health"),
        )
        self._tasks: list[asyncio.Task] = []
        self._cycle = 0

    # ------------------------------------------------------------------
    # Construcao
    # ------------------------------------------------------------------
    def build_monitors(self) -> dict[str, Monitor]:
        settings = self.settings
        self.monitors = {
            C.COMPONENT_GATEWAY: GatewayMonitor(settings),
            C.COMPONENT_SERVER: ServerMonitor(settings, self.http),
            C.COMPONENT_INTERNET: InternetMonitor(settings),
            C.COMPONENT_DNS: DnsMonitor(settings),
            C.COMPONENT_SEFAZ_TCP: SefazTcpMonitor(settings),
            C.COMPONENT_SEFAZ_TLS: SefazTlsMonitor(settings),
        }
        return self.monitors

    # ------------------------------------------------------------------
    # Eventos e snapshots
    # ------------------------------------------------------------------
    async def on_transition(self, transition: Transition) -> None:
        label = C.COMPONENT_LABELS.get(transition.component, transition.component)
        if transition.current:
            severity = "info"
            message = f"{label} recuperado"
        else:
            severity = "critical"
            message = f"{label} em falha"
            if transition.error:
                message = f"{message} - {transition.error}"

        event = EventIn(
            machine_name=self.machine.machine_name,
            timestamp=utc_now(),
            kind="state_change",
            component=transition.component,
            severity=severity,
            message=message,
            payload={
                "previous": transition.previous,
                "current": transition.current,
                "error": transition.error,
                "details": transition.details,
            },
        )
        self.queue.enqueue("event", event.model_dump(mode="json"))
        self.log.warning(
            "%s: %s -> %s%s",
            transition.component,
            transition.previous,
            transition.current,
            f" ({transition.error})" if transition.error else "",
        )

    def build_current_measurement(self):
        measurement = build_measurement(self.machine.machine_name, self.monitors)
        measurement.details["sefaz_authorization_log"] = (
            self.authorization_log.status()
            if self.authorization_log
            else {"configured": False, "available": False}
        )
        return measurement

    async def snapshot_loop(self) -> None:
        while not self.stop_event.is_set():
            # Evita gravar um snapshot vazio antes da primeira coleta
            if not any(monitor.last is not None for monitor in self.monitors.values()):
                await self._sleep(1.0)
                continue
            self._cycle += 1
            try:
                measurement = self.build_current_measurement()
                self.queue.enqueue("measurement", measurement.model_dump(mode="json"))
                self.queue.trim()
            except Exception:  # noqa: BLE001
                self.log.exception("Falha ao montar/enfileirar o snapshot")
            await self._sleep(self.settings.snapshot_interval)

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self.stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def authorization_log_loop(self) -> None:
        while not self.stop_event.is_set():
            if self.authorization_log:
                self.authorization_log.poll()
            await self._sleep(2.0)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    def health_payload(self) -> dict[str, Any]:
        return {
            "status": "ok" if not self.stop_event.is_set() else "stopping",
            "service": "bertolo-agent",
            "machine_name": self.machine.machine_name,
            "hostname": self.machine.hostname,
            "local_ip": self.machine.local_ip,
            "agent_version": self.settings.agent_version,
            "os_version": self.machine.os_version,
            "server_url": self.settings.server_url,
            "uptime_seconds": round(time.time() - self.started_at, 1),
            "cycle": self._cycle,
            "queue": self.queue.stats().as_dict(),
            "sender": self.sender.status(),
            "monitors": {name: monitor.snapshot() for name, monitor in self.monitors.items()},
            "sefaz_authorization_log": (
                self.authorization_log.status() if self.authorization_log else {"configured": False}
            ),
            "time_utc": to_iso(utc_now()),
        }

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    async def start(self) -> None:
        self.build_monitors()
        self.health.start()

        for name, monitor in self.monitors.items():
            self._tasks.append(
                asyncio.create_task(
                    monitor.run(self.on_transition, self.stop_event), name=f"monitor-{name}"
                )
            )
        self._tasks.append(asyncio.create_task(self.snapshot_loop(), name="snapshot"))
        self._tasks.append(asyncio.create_task(self.sender.run(self.stop_event), name="sender"))
        if self.authorization_log:
            self._tasks.append(
                asyncio.create_task(self.authorization_log_loop(), name="sefaz-authorizations")
            )

        self.log.info(
            "Agente iniciado | maquina=%s ip=%s servidor=%s monitores=%s",
            self.machine.machine_name,
            self.machine.local_ip,
            self.settings.server_url,
            ",".join(self.monitors),
        )

    async def stop(self) -> None:
        if self.stop_event.is_set():
            return
        self.log.info("Encerrando o agente...")
        self.stop_event.set()

        try:
            await asyncio.wait_for(self.sender.flush(), timeout=DRAIN_TIMEOUT_SECONDS)
        except Exception:  # noqa: BLE001
            self.log.warning("Nao foi possivel esvaziar a fila no encerramento", exc_info=True)

        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        self.health.stop()
        await self.http.aclose()
        self.queue.close()
        self.log.info("Agente encerrado. Fila final: %s", self.queue.stats().as_dict())

    async def run(self) -> None:
        await self.start()
        try:
            await self.stop_event.wait()
        finally:
            await self.stop()


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, stop_event: asyncio.Event) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, AttributeError, ValueError, RuntimeError):
            # No Windows add_signal_handler nao existe; o servico e parado
            # pelo WinSW/sc.exe, que encerra o processo.
            continue


async def run_forever(settings: AgentSettings) -> int:
    if not settings.agent_ingest_token:
        raise SystemExit("AGENT_INGEST_TOKEN obrigatorio para iniciar o agente em modo continuo.")
    agent = Agent(settings)
    loop = asyncio.get_running_loop()
    _install_signal_handlers(loop, agent.stop_event)
    await agent.run()
    return 0


async def run_once(settings: AgentSettings) -> int:
    """Executa uma unica rodada de todos os monitores e imprime JSON."""
    agent = Agent(settings)
    agent.build_monitors()
    monitors = list(agent.monitors.values())
    results = await asyncio.gather(*(monitor.check() for monitor in monitors), return_exceptions=True)

    for monitor, result in zip(monitors, results):
        if isinstance(result, BaseException):
            monitor.errors += 1
            monitor.last_error = f"{type(result).__name__}: {result}"
            monitor.last = CheckResult(
                component=monitor.component,
                ok=False,
                error=monitor.last_error,
                checked_at=to_iso(utc_now()),
            )
        else:
            result.checked_at = to_iso(utc_now())
            monitor.last = result
        monitor.checks += 1
        if monitor.last.ok:
            monitor.consecutive_ok = 1
            monitor.consecutive_fail = 0
        elif monitor.last.ok is False:
            monitor.consecutive_fail = 1
            monitor.consecutive_ok = 0

    measurement = agent.build_current_measurement()
    payload = {
        "machine": json.loads(agent.machine.model_dump_json()),
        "measurement": json.loads(measurement.model_dump_json()),
        "monitors": {name: monitor.snapshot() for name, monitor in agent.monitors.items()},
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    await agent.http.aclose()
    agent.queue.close()
    return 0


def _config_payload(settings: AgentSettings) -> dict[str, Any]:
    return {
        "machine_name": settings.machine_name,
        "store_name": settings.store_name,
        "server_url": settings.server_url,
        "server_ca_file": str(settings.server_ca_file) if settings.server_ca_file else None,
        "agent_ingest_token_configured": bool(settings.agent_ingest_token),
        "sefaz_authorization_log_configured": settings.sefaz_authorization_log_path is not None,
        "server_ip": settings.server_ip,
        "gateway_ip": settings.gateway_ip,
        "sefaz": f"{settings.sefaz_host}:{settings.sefaz_port}",
        "internet_targets": settings.internet_targets,
        "external_dns_servers": settings.external_dns_servers,
        "intervals": settings.intervals,
        "snapshot_interval": settings.snapshot_interval,
        "sender_interval": settings.sender_interval,
        "health": f"{settings.health_host}:{settings.health_port}",
        "agent_version": settings.agent_version,
        "base_dir": str(settings.base_dir),
        "data_dir": str(settings.data_dir),
        "log_dir": str(settings.log_dir),
        "queue_path": str(settings.queue_path),
        "env_file": str(settings.env_file) if settings.env_file else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bertolo-agent", description="Agente Bertolo Monitor")
    parser.add_argument("--once", action="store_true", help="executa uma rodada e imprime JSON")
    parser.add_argument("--print-config", action="store_true", help="imprime a configuracao efetiva")
    parser.add_argument("--version", action="version", version=C.AGENT_VERSION)
    args = parser.parse_args(argv)

    settings = AgentSettings.from_env()
    settings.ensure_dirs()
    setup_logging(settings.log_dir, settings.log_level)

    if args.print_config:
        print(json.dumps(_config_payload(settings), ensure_ascii=False, indent=2))
        return 0

    if args.once:
        return asyncio.run(run_once(settings))

    try:
        return asyncio.run(run_forever(settings))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
