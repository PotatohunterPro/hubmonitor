"""Infraestrutura comum dos monitores.

Regra do projeto (plano secao 4.8): a falha de um monitor nunca pode
encerrar o processo. Cada monitor roda em sua propria tarefa asyncio e
qualquer excecao vira um resultado de falha, nunca um crash.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from shared.timeutil import to_iso, utc_now

TransitionCallback = Callable[["Transition"], Awaitable[None]]


@dataclass(slots=True)
class CheckResult:
    component: str
    ok: bool | None
    latency_ms: float | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    checked_at: str | None = None


@dataclass(slots=True)
class Transition:
    """Transicao do estado instantaneo de um componente."""

    component: str
    previous: bool | None
    current: bool | None
    at: float
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class Monitor:
    """Monitor periodico com estado e deteccao de transicao."""

    component: str = "unknown"

    def __init__(self, interval: float, logger: logging.Logger | None = None) -> None:
        self.interval = max(1.0, float(interval))
        self.log = logger or logging.getLogger(f"agent.monitor.{self.component}")
        self.last: CheckResult | None = None
        self.consecutive_ok = 0
        self.consecutive_fail = 0
        self.checks = 0
        self.errors = 0
        self.last_error: str | None = None
        self.last_duration_ms: float | None = None

    async def check(self) -> CheckResult:  # pragma: no cover - interface
        raise NotImplementedError

    async def run(self, on_transition: TransitionCallback | None = None, stop: asyncio.Event | None = None) -> None:
        """Loop perpetuo do monitor."""
        stop = stop or asyncio.Event()
        while not stop.is_set():
            started = time.perf_counter()
            previous = self.last.ok if self.last else None
            try:
                result = await self.check()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - monitor nunca derruba o agente
                self.errors += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.log.exception("Falha inesperada no monitor %s", self.component)
                result = CheckResult(component=self.component, ok=False, error=self.last_error)

            self.checks += 1
            self.last_duration_ms = round((time.perf_counter() - started) * 1000.0, 1)
            result.checked_at = to_iso(utc_now())
            self.last = result
            if result.ok:
                self.consecutive_ok += 1
                self.consecutive_fail = 0
            elif result.ok is False:
                self.consecutive_fail += 1
                self.consecutive_ok = 0
                self.last_error = result.error

            if on_transition and result.ok is not None and result.ok != previous:
                await on_transition(
                    Transition(
                        component=self.component,
                        previous=previous,
                        current=result.ok,
                        at=time.time(),
                        error=result.error,
                        details=result.details,
                    )
                )

            elapsed = time.perf_counter() - started
            await _sleep_unless_stopped(max(0.2, self.interval - elapsed), stop)

    def snapshot(self) -> dict[str, Any]:
        """Estado atual resumido (usado no health local)."""
        return {
            "component": self.component,
            "ok": self.last.ok if self.last else None,
            "latency_ms": self.last.latency_ms if self.last else None,
            "error": self.last.error if self.last else None,
            "consecutive_ok": self.consecutive_ok,
            "consecutive_fail": self.consecutive_fail,
            "checks": self.checks,
            "errors": self.errors,
            "last_duration_ms": self.last_duration_ms,
            "checked_at": self.last.checked_at if self.last else None,
        }


async def _sleep_unless_stopped(seconds: float, stop: asyncio.Event) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass
