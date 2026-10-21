"""Motor de ocorrencias: historico observado, nao inferido.

Principios (pedido do cliente):

  - a primeira falha observada e persistida, mesmo antes da confirmacao;
  - a ocorrencia so e confirmada depois de N falhas consecutivas;
  - a recuperacao tambem exige N sucessos consecutivos;
  - o horario de cada observacao e o horario ORIGINAL do agente, mesmo que
    o dado chegue horas depois (replay apos reconexao);
  - periodos sem observacao nao viram falha nem duracao: sao contabilizados
    como lacuna (unobserved_seconds);
  - a duracao registrada e a janela efetivamente observada, distinta do
    momento de confirmacao;
  - sintomas dependentes (DNS/SEFAZ quando a Internet caiu) sao consolidados
    em uma unica ocorrencia raiz, sem alertas redundantes.

O motor e idempotente: reenviar o mesmo lote nao duplica nada, porque cada
observacao so avanca o estado se for mais nova que a ultima processada.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Mapping, Sequence

from server.config import ServerSettings
from server.database.db import Database
from server.services import diagnostics as diag
from shared import constants as C
from shared.timeutil import parse_iso, to_iso, utc_now

#: Acima deste intervalo entre duas observacoes do mesmo componente, o
#: periodo e tratado como "sem observacao" (agente desligado, sem rede).
GAP_THRESHOLD_SECONDS = 45.0

#: Componentes que geram ocorrencia. TEF fica de fora nesta versao.
INCIDENT_COMPONENTS: tuple[str, ...] = (
    C.COMPONENT_GATEWAY,
    C.COMPONENT_SERVER,
    C.COMPONENT_INTERNET,
    C.COMPONENT_DNS,
    C.COMPONENT_SEFAZ_TCP,
    C.COMPONENT_SEFAZ_TLS,
)

#: Componente -> causas que explicam o sintoma.
SYMPTOM_OF: dict[str, tuple[str, ...]] = {
    C.COMPONENT_DNS: (C.COMPONENT_INTERNET, C.COMPONENT_GATEWAY),
    C.COMPONENT_SEFAZ_TCP: (C.COMPONENT_DNS, C.COMPONENT_INTERNET, C.COMPONENT_GATEWAY),
    C.COMPONENT_SEFAZ_TLS: (
        C.COMPONENT_SEFAZ_TCP,
        C.COMPONENT_DNS,
        C.COMPONENT_INTERNET,
        C.COMPONENT_GATEWAY,
    ),
    C.COMPONENT_INTERNET: (C.COMPONENT_GATEWAY,),
    C.COMPONENT_SERVER: (),
}

CONSOLIDATION_TOLERANCE_SECONDS = 30.0


@dataclass(slots=True)
class Observation:
    machine: str
    component: str
    observed_at: datetime
    ok: bool
    source: str = "live"


@dataclass(slots=True)
class OccurrenceEvent:
    action: str  # open | update | recover
    incident_id: int
    component: str
    machine: str


Enricher = Callable[[int, str, list[str]], None]


def _blank_state(machine: str, component: str) -> dict[str, Any]:
    return {
        "machine_name": machine,
        "component": component,
        "consecutive_fail": 0,
        "consecutive_ok": 0,
        "first_fail_at": None,
        "first_ok_at": None,
        "last_observed_at": None,
        "incident_id": None,
        "unobserved_seconds": 0.0,
    }


class OccurrenceEngine:
    def __init__(
        self,
        db: Database,
        settings: ServerSettings,
        logger: logging.Logger | None = None,
        enricher: Enricher | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.log = logger or logging.getLogger("server.occurrences")
        self.enricher = enricher
        self.failure_threshold = max(1, int(settings.incident_failure_threshold))
        self.recovery_threshold = max(1, int(settings.incident_recovery_threshold))

    # ------------------------------------------------------------------
    # Entrada principal
    # ------------------------------------------------------------------
    def observe(self, observations: Iterable[Observation]) -> list[OccurrenceEvent]:
        grouped: dict[tuple[str, str], list[Observation]] = {}
        for item in observations:
            if item.component not in INCIDENT_COMPONENTS:
                continue
            key = (item.machine.strip().upper(), item.component)
            grouped.setdefault(key, []).append(item)

        if not grouped:
            return []

        states = self.db.get_occurrence_states()
        events: list[OccurrenceEvent] = []

        for (machine, component), items in sorted(grouped.items()):
            items.sort(key=lambda entry: entry.observed_at)
            state = states.get((machine, component)) or _blank_state(machine, component)
            produced, state = self._process(machine, component, state, items)
            events.extend(produced)
            self.db.set_occurrence_state(
                machine,
                component,
                consecutive_fail=state["consecutive_fail"],
                consecutive_ok=state["consecutive_ok"],
                first_fail_at=state["first_fail_at"],
                first_ok_at=state["first_ok_at"],
                last_observed_at=state["last_observed_at"],
                incident_id=state["incident_id"],
                unobserved_seconds=state["unobserved_seconds"],
            )

        self.consolidate()
        return events

    # ------------------------------------------------------------------
    # Maquina de estados por (maquina, componente)
    # ------------------------------------------------------------------
    def _process(
        self,
        machine: str,
        component: str,
        state: dict[str, Any],
        items: Sequence[Observation],
    ) -> tuple[list[OccurrenceEvent], dict[str, Any]]:
        events: list[OccurrenceEvent] = []

        fail_count = int(state.get("consecutive_fail") or 0)
        ok_count = int(state.get("consecutive_ok") or 0)
        first_fail = parse_iso(state.get("first_fail_at"))
        first_ok = parse_iso(state.get("first_ok_at"))
        last_observed = parse_iso(state.get("last_observed_at"))
        incident_id = state.get("incident_id")
        unobserved = float(state.get("unobserved_seconds") or 0.0)

        for item in items:
            stamp = item.observed_at
            if last_observed is not None and stamp <= last_observed:
                continue  # reenvio ou observacao ja processada

            if incident_id is not None and last_observed is not None:
                gap = (stamp - last_observed).total_seconds()
                if gap > GAP_THRESHOLD_SECONDS:
                    unobserved += gap

            if item.ok:
                ok_count += 1
                fail_count = 0
                if incident_id is not None and first_ok is None:
                    first_ok = stamp
                if incident_id is not None and ok_count >= self.recovery_threshold:
                    event = self._recover(
                        machine, component, incident_id, stamp, first_fail, first_ok, unobserved
                    )
                    if event is not None:
                        events.append(event)
                    incident_id = None
                    first_fail = None
                    first_ok = None
                    unobserved = 0.0
                    fail_count = 0
                    ok_count = 0
            else:
                fail_count += 1
                ok_count = 0
                if first_fail is None:
                    first_fail = stamp
                if incident_id is None and fail_count >= self.failure_threshold:
                    incident_id, event = self._open(
                        machine, component, stamp, first_fail, item.source
                    )
                    if event is not None:
                        events.append(event)
                    first_ok = None
                    unobserved = 0.0

            last_observed = stamp

        new_state = {
            "machine_name": machine,
            "component": component,
            "consecutive_fail": fail_count,
            "consecutive_ok": ok_count,
            "first_fail_at": to_iso(first_fail) if first_fail else None,
            "first_ok_at": to_iso(first_ok) if first_ok else None,
            "last_observed_at": to_iso(last_observed) if last_observed else None,
            "incident_id": incident_id,
            "unobserved_seconds": round(unobserved, 3),
        }
        return events, new_state

    # ------------------------------------------------------------------
    def _open(
        self,
        machine: str,
        component: str,
        confirmed_at: datetime,
        first_fail_at: datetime,
        source: str,
    ) -> tuple[int | None, OccurrenceEvent | None]:
        incident = self.db.open_incident(component)

        if incident is None:
            incident_id = self.db.create_incident(
                component,
                "warning",
                to_iso(first_fail_at),
                [machine],
                None,
                None,
            )
            self.db.set_incident_observation(
                incident_id,
                first_fail_at=to_iso(first_fail_at),
                confirmed_at=to_iso(confirmed_at),
                source=source,
            )
            self.db.enqueue_notification(f"{incident_id}:open", incident_id, "open")
            if self.enricher is not None:
                self.enricher(incident_id, component, [machine])
            self.log.warning(
                "Ocorrencia #%s aberta: %s em %s (primeira falha %s, confirmada %s)",
                incident_id,
                component,
                machine,
                to_iso(first_fail_at),
                to_iso(confirmed_at),
            )
            return incident_id, OccurrenceEvent("open", incident_id, component, machine)

        incident_id = int(incident["id"])
        # open_incident devolve a linha crua: affected_machines e JSON em texto.
        current = self.db.incident_by_id(incident_id) or incident
        machines = set(current.get("affected_machines") or []) | {machine}
        self.db.set_incident_machines(incident_id, sorted(machines))
        self.db.set_incident_observation(
            incident_id, first_fail_at=to_iso(first_fail_at), source=source
        )
        if self.enricher is not None:
            self.enricher(incident_id, component, sorted(machines))
        self.log.info(
            "Ocorrencia #%s agregada: %s agora afeta %s",
            incident_id,
            component,
            sorted(machines),
        )
        return incident_id, OccurrenceEvent("update", incident_id, component, machine)

    # ------------------------------------------------------------------
    def _recover(
        self,
        machine: str,
        component: str,
        incident_id: int,
        recovered_at: datetime,
        first_fail_at: datetime | None,
        first_ok_at: datetime | None,
        unobserved: float,
    ) -> OccurrenceEvent | None:
        incident = self.db.incident_by_id(incident_id)
        if incident is None:
            return None

        remaining = [item for item in (incident.get("affected_machines") or []) if item != machine]
        if remaining:
            self.db.set_incident_machines(incident_id, remaining)
            if self.enricher is not None:
                self.enricher(incident_id, component, remaining)
            return OccurrenceEvent("update", incident_id, component, machine)

        observed_seconds: float | None = None
        if first_fail_at is not None:
            observed_seconds = round(
                max(0.0, (recovered_at - first_fail_at).total_seconds() - float(unobserved or 0.0)),
                3,
            )

        self.db.finalize_incident(
            incident_id,
            recovered_at=to_iso(recovered_at),
            first_ok_at=to_iso(first_ok_at),
            observed_duration_seconds=observed_seconds,
            unobserved_seconds=round(float(unobserved or 0.0), 3),
        )
        self.db.enqueue_notification(f"{incident_id}:recovery", incident_id, "recovery")
        self.log.info(
            "Ocorrencia #%s recuperada: %s em %s (observado %ss, lacuna %ss)",
            incident_id,
            component,
            machine,
            observed_seconds,
            round(float(unobserved or 0.0), 3),
        )
        return OccurrenceEvent("recover", incident_id, component, machine)

    # ------------------------------------------------------------------
    # Consolidacao de sintomas dependentes
    # ------------------------------------------------------------------
    def consolidate(self, hours: int = 48) -> int:
        """Marca como sintoma as ocorrencias explicadas por uma causa raiz."""
        since = to_iso(utc_now() - timedelta(hours=hours))
        incidents = self.db.incidents_since(since)
        if not incidents:
            return 0

        by_type: dict[str, list[dict[str, Any]]] = {}
        for incident in incidents:
            by_type.setdefault(str(incident.get("type")), []).append(incident)

        marked = 0
        for child in incidents:
            if child.get("suppressed_by"):
                continue
            root = self._covering_root(child, by_type)
            if root is None:
                continue
            self.db.set_incident_suppressed(int(child["id"]), int(root["id"]))
            self.db.cancel_notification(f"{child['id']}:open", "consolidada em ocorrencia raiz")
            self.db.cancel_notification(f"{child['id']}:recovery", "consolidada em ocorrencia raiz")
            marked += 1
        return marked

    def _covering_root(
        self, child: Mapping[str, Any], by_type: Mapping[str, Sequence[Mapping[str, Any]]]
    ) -> Mapping[str, Any] | None:
        child_start = parse_iso(child.get("started_at"))
        child_end = parse_iso(child.get("recovered_at")) or utc_now()
        if child_start is None:
            return None

        candidates: list[Mapping[str, Any]] = []
        for component in SYMPTOM_OF.get(str(child.get("type")), ()):
            for incident in by_type.get(component, ()):
                if incident.get("id") == child.get("id"):
                    continue
                start = parse_iso(incident.get("started_at"))
                if start is None:
                    continue
                end = parse_iso(incident.get("recovered_at")) or utc_now()
                if start - timedelta(seconds=CONSOLIDATION_TOLERANCE_SECONDS) > child_start:
                    continue
                if end + timedelta(seconds=CONSOLIDATION_TOLERANCE_SECONDS) < child_end:
                    continue
                candidates.append(incident)

        if not candidates:
            return None
        candidates.sort(key=lambda item: parse_iso(item.get("started_at")) or utc_now())
        return candidates[0]

    # ------------------------------------------------------------------
    # Reconstrucao a partir do historico (replay apos reconexao)
    # ------------------------------------------------------------------
    def reconstruct(self, machine: str, hours: int = 24, limit: int = 5000) -> list[OccurrenceEvent]:
        """Reprocessa o historico do caixa, reconstruindo ocorrencias perdidas.

        E idempotente: observacoes ja processadas sao ignoradas pelo
        watermark de last_observed_at.
        """
        rows = self.db.machine_history(machine, hours=hours, limit=limit)
        observations: list[Observation] = []
        for row in rows:
            stamp = parse_iso(row.get("timestamp"))
            if stamp is None:
                continue
            for component in INCIDENT_COMPONENTS:
                column = diag.COMPONENT_STATUS_FIELD.get(component)
                if not column:
                    continue
                value = row.get(column)
                if value is None:
                    continue
                observations.append(Observation(machine, component, stamp, bool(value), "replay"))
        return self.observe(observations)


def plan_notification(row: Mapping[str, Any]) -> str:
    """Decide o tipo de mensagem para uma notificacao pendente.

    Retorna: open | recovery | retrospective | skip.
    """
    if row.get("suppressed_by"):
        return "skip"

    kind = str(row.get("notification_kind") or "")
    if kind == "open":
        if row.get("recovered_at") is None:
            return "open"
        # A ocorrencia terminou antes de conseguirmos avisar: uma unica
        # mensagem retrospectiva, nunca um alerta de falha "atual".
        return "retrospective"

    if not row.get("telegram_sent"):
        return "retrospective"
    return "recovery"
