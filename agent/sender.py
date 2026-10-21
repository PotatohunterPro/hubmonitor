"""Envio dos dados enfileirados para o servidor central.

Implementa o ciclo do plano secao 8: tenta enviar, marca falha e volta
depois com backoff. O timestamp original de cada item e preservado
porque ele viaja dentro do payload.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from agent.config import AgentSettings
from agent.queue.local_queue import LocalQueue
from shared.schemas import MachineInfo
from shared.timeutil import utc_now

MEASUREMENT_BATCH = 240
EVENT_BATCH = 240
MAX_BACKOFF_SECONDS = 60.0


class Sender:
    def __init__(
        self,
        settings: AgentSettings,
        queue: LocalQueue,
        http: httpx.AsyncClient,
        machine: MachineInfo,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings
        self.queue = queue
        self.http = http
        self.machine = machine
        self.log = logger or logging.getLogger("agent.sender")
        self.last_success_at: float | None = None
        self.last_error: str | None = None
        self.consecutive_failures = 0
        self._backoff_until = 0.0
        self.sent_total = 0

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            if time.time() >= self._backoff_until:
                try:
                    await self.flush()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    self.log.exception("Erro inesperado no sender: %s", exc)
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.settings.sender_interval)
            except asyncio.TimeoutError:
                pass

    async def flush(self) -> bool:
        measurements = self.queue.pending("measurement", MEASUREMENT_BATCH)
        events = self.queue.pending("event", EVENT_BATCH)
        authorizations = self.queue.pending("sefaz_authorization", EVENT_BATCH)
        if not measurements and not events and not authorizations:
            self.consecutive_failures = 0
            return True

        ok = True
        if measurements:
            ok = await self._send(measurements, "measurements", self.settings.measurements_url) and ok
        if events:
            ok = await self._send(events, "events", self.settings.events_url) and ok
        if authorizations:
            ok = (
                await self._send(
                    authorizations, "authorizations", self.settings.authorizations_url
                )
            ) and ok

        if ok:
            self.consecutive_failures = 0
            self._backoff_until = 0.0
            self.last_success_at = time.time()
            self.last_error = None
        else:
            self.consecutive_failures += 1
            delay = min(MAX_BACKOFF_SECONDS, self.settings.sender_interval * (2 ** min(self.consecutive_failures, 4)))
            self._backoff_until = time.time() + delay
            self.queue.bump_counter("send_failures")
            self.log.warning(
                "Servidor indisponivel (%d falhas seguidas). Nova tentativa em %.0fs. Fila: %s",
                self.consecutive_failures,
                delay,
                self.queue.stats().as_dict(),
            )
        return ok

    async def _send(self, rows: list[Any], field: str, url: str) -> bool:
        self.machine.collected_at = utc_now()  # mantem machines.last_seen fresco
        payload: dict[str, Any] = {
            "machine": json.loads(self.machine.model_dump_json()),
            field: [json.loads(row["payload"]) for row in rows],
        }
        ids = [int(row["id"]) for row in rows]
        try:
            response = await self.http.post(url, json=payload, timeout=10.0)
        except Exception as exc:  # noqa: BLE001 - rede caiu, fila segura o dado
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.queue.mark_failed(ids, self.last_error)
            return False

        if response.status_code >= 400:
            self.last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            self.queue.mark_failed(ids, self.last_error)
            return False

        removed = self.queue.delete(ids)
        self.sent_total += removed
        self.queue.bump_counter("sent_total", removed)
        self.log.debug("Enviados %d itens para %s", removed, url)
        return True

    def status(self) -> dict[str, Any]:
        return {
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
            "sent_total": self.sent_total,
            "server_time": utc_now().isoformat(),
        }
