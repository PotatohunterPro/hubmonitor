"""Deteccao de incidentes: adaptador sobre o motor de ocorrencias.

A API publica (IncidentManager.evaluate / pending_notifications) foi
mantida para nao quebrar o restante do servidor, mas a logica de estado
agora vive em server.services.occurrences, que trata replay, lacunas e
consolidacao de sintomas.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from server.config import ServerSettings
from server.database.db import Database
from server.services import diagnostics as diag
from server.services.occurrences import (
    INCIDENT_COMPONENTS,
    Observation,
    OccurrenceEngine,
    plan_notification,
)
from shared.timeutil import parse_iso, utc_now


@dataclass(slots=True)
class IncidentEvent:
    action: str  # opened | updated | recovered
    incident_id: int
    incident: dict[str, Any] = field(default_factory=dict)


class IncidentManager:
    def __init__(
        self,
        db: Database,
        settings: ServerSettings,
        logger: logging.Logger | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.log = logger or logging.getLogger("server.incidents")
        self._statuses: dict[str, Mapping[str, Any]] = {}
        self._wans: Sequence[Mapping[str, Any]] = []
        self.engine = OccurrenceEngine(db, settings, self.log, enricher=self._enrich)

    # ------------------------------------------------------------------
    def _enrich(self, incident_id: int, component: str, machines: list[str]) -> None:
        diagnosis = diag.fleet_diagnosis(
            component, machines, self._statuses, self._wans, len(self._statuses)
        )
        self.db.update_incident(
            incident_id,
            affected_machines=machines,
            diagnosis=diagnosis,
            active_wan=diag.active_wan_from_statuses(self._wans),
            severity=diag.incident_severity(component, machines),
        )

    # ------------------------------------------------------------------
    def evaluate(
        self,
        statuses: Mapping[str, Mapping[str, Any]],
        wan_statuses: Sequence[Mapping[str, Any]],
    ) -> list[IncidentEvent]:
        self._statuses = dict(statuses)
        self._wans = list(wan_statuses)

        now = utc_now()
        observations: list[Observation] = []
        for machine, status in statuses.items():
            if status.get("online") is False:
                continue  # sem dados do caixa: nao conta falha de componente
            stamps = status.get("check_timestamps") or {}
            for component in INCIDENT_COMPONENTS:
                stamp = parse_iso(stamps.get(component))
                if stamp is None:
                    continue
                ok = diag.component_status(status, component)
                if ok is None:
                    continue
                # Dado que chega muito depois do ocorrido veio da fila local
                # apos reconexao: e reconstrucao, nao observacao ao vivo.
                source = "replay" if (now - stamp).total_seconds() > 120 else "live"
                observations.append(Observation(machine, component, stamp, ok, source))

        events: list[IncidentEvent] = []
        for produced in self.engine.observe(observations):
            incident = self.db.incident_by_id(produced.incident_id)
            if incident is None:
                continue
            events.append(
                IncidentEvent(
                    action=produced.action,
                    incident_id=produced.incident_id,
                    incident=incident,
                )
            )
        return events

    # ------------------------------------------------------------------
    def reconstruct(self, machine: str, hours: int = 24, limit: int = 5000) -> list[IncidentEvent]:
        """Reconstroi ocorrencias a partir do historico reenviado pelo caixa."""
        events: list[IncidentEvent] = []
        for produced in self.engine.reconstruct(machine, hours=hours, limit=limit):
            incident = self.db.incident_by_id(produced.incident_id)
            if incident is None:
                continue
            events.append(
                IncidentEvent(
                    action=produced.action,
                    incident_id=produced.incident_id,
                    incident=incident,
                )
            )
        return events

    # ------------------------------------------------------------------
    def pending_notifications(self) -> list[tuple[str, dict[str, Any]]]:
        """Notificacoes pendentes no formato legado (kind, incidente)."""
        pending: list[tuple[str, dict[str, Any]]] = []
        for row in self.db.pending_notification_rows(limit=50):
            plan = plan_notification(row)
            if plan == "skip":
                continue
            incident = self.db.incident_by_id(int(row["incident_id"]))
            if incident is None:
                continue
            if plan in ("open", "retrospective"):
                if incident.get("telegram_sent"):
                    continue
                pending.append(("open", incident))
            else:
                if incident.get("telegram_recovery_sent"):
                    continue
                pending.append(("recover", incident))
        return pending

    def notification_plans(self) -> list[tuple[str, dict[str, Any]]]:
        """(plano, linha) para o laco de envio, uma por ocorrencia.

        Uma ocorrencia fechada antes do aviso tem DUAS linhas pendentes
        (abertura e recuperacao). Se ambas virarem "retrospective", o
        laco enviaria a mesma historia duas vezes. Aqui colapsamos para
        uma linha por incidente; as demais sao canceladas pelo envio.
        """
        plans: list[tuple[str, dict[str, Any]]] = []
        vistos: set[int] = set()
        for row in self.db.pending_notification_rows(limit=50):
            incident_id = int(row["incident_id"])
            plan = plan_notification(row)
            if plan == "skip":
                self.db.cancel_notification(str(row["dedupe_key"]), "sintoma de causa raiz")
                continue
            if incident_id in vistos:
                continue
            vistos.add(incident_id)
            plans.append((plan, row))
        return plans

    @staticmethod
    def serialize_machines(machines: Sequence[str]) -> str:
        import json

        return json.dumps(sorted(set(machines)))
