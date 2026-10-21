"""Persistencia SQLite do servidor central.

Decisao de projeto: os caixas NUNCA escrevem direto no banco. Todo dado
entra por API (plano secao 10). Este modulo e usado apenas pelo servidor.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable

from shared import constants as C
from shared.schemas import EventIn, Measurement, MachineInfo, SefazAuthorization, WanStatus
from shared.timeutil import ensure_utc, parse_iso, to_iso, utc_now

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS machines (
    machine_name  TEXT PRIMARY KEY,
    hostname      TEXT,
    local_ip      TEXT,
    agent_version TEXT,
    os_version    TEXT,
    created_at    TEXT NOT NULL,
    last_seen     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS measurements (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp              TEXT NOT NULL,
    machine_name           TEXT NOT NULL,
    received_at            TEXT NOT NULL,
    gateway_ok             INTEGER,
    gateway_latency_ms     REAL,
    gateway_loss_pct       REAL,
    server_ok              INTEGER,
    server_latency_ms      REAL,
    server_loss_pct        REAL,
    internet_ok            INTEGER,
    internet_latency_ms    REAL,
    internet_targets_ok    INTEGER,
    internet_targets_total INTEGER,
    dns_ok                 INTEGER,
    dns_latency_ms         REAL,
    dns_resolver           TEXT,
    dns_system_ok          INTEGER,
    dns_external_ok        INTEGER,
    resolved_ips           TEXT,
    dns_error              TEXT,
    sefaz_tcp_ok           INTEGER,
    sefaz_tcp_latency_ms   REAL,
    sefaz_tcp_ip           TEXT,
    sefaz_tcp_error        TEXT,
    sefaz_tls_ok           INTEGER,
    sefaz_tls_latency_ms   REAL,
    sefaz_tls_protocol     TEXT,
    sefaz_cert_subject     TEXT,
    sefaz_cert_not_after   TEXT,
    sefaz_cert_days_left   INTEGER,
    sefaz_tls_verify_ok    INTEGER,
    sefaz_tls_error        TEXT,
    tef_connected          INTEGER,
    tef_remote_ip          TEXT,
    tef_remote_port        INTEGER,
    tef_connections        INTEGER,
    active_wan             TEXT,
    diagnosis              TEXT,
    details                TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_measurements_unique
    ON measurements (machine_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_measurements_machine_ts
    ON measurements (machine_name, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_measurements_ts
    ON measurements (timestamp DESC);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT NOT NULL,
    machine_name TEXT NOT NULL,
    received_at  TEXT NOT NULL,
    kind         TEXT NOT NULL,
    component    TEXT,
    severity     TEXT NOT NULL DEFAULT 'info',
    message      TEXT,
    payload      TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_events_unique
    ON events (machine_name, timestamp, kind, component);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events (timestamp DESC);

CREATE TABLE IF NOT EXISTS incidents (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    type                   TEXT NOT NULL,
    severity               TEXT NOT NULL DEFAULT 'warning',
    started_at             TEXT NOT NULL,
    recovered_at           TEXT,
    duration_seconds       REAL,
    affected_machines      TEXT NOT NULL DEFAULT '[]',
    active_wan             TEXT,
    diagnosis              TEXT,
    telegram_sent          INTEGER NOT NULL DEFAULT 0,
    telegram_recovery_sent INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_incidents_started ON incidents (started_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_incidents_open_unique
    ON incidents (type) WHERE recovered_at IS NULL;

CREATE TABLE IF NOT EXISTS wan_status (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT NOT NULL,
    wan_name     TEXT NOT NULL,
    provider     TEXT,
    status       TEXT NOT NULL DEFAULT 'unknown',
    probe        TEXT,
    latency_ms   REAL,
    active_route INTEGER,
    loss_pct     REAL
);

CREATE INDEX IF NOT EXISTS idx_wan_status_name_ts ON wan_status (wan_name, timestamp DESC);

CREATE TABLE IF NOT EXISTS wan_alert_state (
    wan_name          TEXT PRIMARY KEY,
    provider           TEXT NOT NULL,
    confirmed_status   TEXT NOT NULL DEFAULT 'unknown',
    candidate_status   TEXT,
    candidate_count    INTEGER NOT NULL DEFAULT 0,
    candidate_since    TEXT,
    last_observed_at   TEXT,
    first_fail_at      TEXT,
    down_confirmed_at  TEXT,
    down_dedupe_key    TEXT,
    updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wan_alert_outbox (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key            TEXT NOT NULL UNIQUE,
    wan_name              TEXT NOT NULL,
    provider              TEXT NOT NULL,
    kind                  TEXT NOT NULL,
    first_fail_at         TEXT NOT NULL,
    down_confirmed_at     TEXT NOT NULL,
    recovered_at          TEXT,
    recovery_confirmed_at TEXT,
    duration_seconds      REAL,
    probe                 TEXT,
    active_route          INTEGER,
    created_at            TEXT NOT NULL,
    sent_at               TEXT,
    attempts              INTEGER NOT NULL DEFAULT 0,
    last_error            TEXT,
    claimed_until         TEXT,
    next_attempt_at       TEXT
);

CREATE INDEX IF NOT EXISTS idx_wan_alert_outbox_pending
    ON wan_alert_outbox (sent_at, id);

CREATE TABLE IF NOT EXISTS component_state (
    machine_name     TEXT NOT NULL,
    component        TEXT NOT NULL,
    last_status      INTEGER,
    consecutive_fail INTEGER NOT NULL DEFAULT 0,
    consecutive_ok   INTEGER NOT NULL DEFAULT 0,
    last_change_at   TEXT,
    last_check_at    TEXT,
    updated_at       TEXT NOT NULL,
    PRIMARY KEY (machine_name, component)
);

CREATE TABLE IF NOT EXISTS occurrence_state (
    machine_name       TEXT NOT NULL,
    component          TEXT NOT NULL,
    consecutive_fail   INTEGER NOT NULL DEFAULT 0,
    consecutive_ok     INTEGER NOT NULL DEFAULT 0,
    first_fail_at      TEXT,
    first_ok_at        TEXT,
    last_observed_at   TEXT,
    incident_id        INTEGER,
    unobserved_seconds REAL NOT NULL DEFAULT 0,
    updated_at         TEXT NOT NULL,
    PRIMARY KEY (machine_name, component)
);

CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key  TEXT NOT NULL UNIQUE,
    incident_id INTEGER NOT NULL,
    kind        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    sent_at     TEXT,
    attempts    INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT
);

CREATE INDEX IF NOT EXISTS idx_notifications_pending
    ON notifications (sent_at, id);

CREATE TABLE IF NOT EXISTS sefaz_authorizations (
    event_id     TEXT NOT NULL,
    machine_name TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    received_at  TEXT NOT NULL,
    duration_ms  INTEGER NOT NULL,
    outcome      TEXT NOT NULL,
    PRIMARY KEY (machine_name, event_id)
);
CREATE INDEX IF NOT EXISTS idx_sefaz_auth_machine_started
    ON sefaz_authorizations (machine_name, started_at DESC);
"""

MEASUREMENT_COLUMNS = [
    "timestamp",
    "machine_name",
    "received_at",
    "gateway_ok",
    "gateway_latency_ms",
    "gateway_loss_pct",
    "server_ok",
    "server_latency_ms",
    "server_loss_pct",
    "internet_ok",
    "internet_latency_ms",
    "internet_targets_ok",
    "internet_targets_total",
    "dns_ok",
    "dns_latency_ms",
    "dns_resolver",
    "dns_system_ok",
    "dns_external_ok",
    "resolved_ips",
    "dns_error",
    "sefaz_tcp_ok",
    "sefaz_tcp_latency_ms",
    "sefaz_tcp_ip",
    "sefaz_tcp_error",
    "sefaz_tls_ok",
    "sefaz_tls_latency_ms",
    "sefaz_tls_protocol",
    "sefaz_cert_subject",
    "sefaz_cert_not_after",
    "sefaz_cert_days_left",
    "sefaz_tls_verify_ok",
    "sefaz_tls_error",
    "tef_connected",
    "tef_remote_ip",
    "tef_remote_port",
    "tef_connections",
    "active_wan",
    "diagnosis",
    "details",
]


def _bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _int_to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


class Database:
    """Acesso ao SQLite com uma conexao unica protegida por lock."""

    def __init__(self, path: Path, logger: logging.Logger | None = None) -> None:
        self.path = Path(path)
        self.log = logger or logging.getLogger("server.db")
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            state_columns = {
                row["name"] for row in self._conn.execute("PRAGMA table_info(component_state)")
            }
            if "last_check_at" not in state_columns:
                self._conn.execute("ALTER TABLE component_state ADD COLUMN last_check_at TEXT")

            wan_outbox_columns = {
                row["name"] for row in self._conn.execute("PRAGMA table_info(wan_alert_outbox)")
            }
            for column in ("claimed_until", "next_attempt_at"):
                if column not in wan_outbox_columns:
                    self._conn.execute(
                        f"ALTER TABLE wan_alert_outbox ADD COLUMN {column} TEXT"
                    )

            # Colunas de ocorrencia: primeira falha, confirmacao, retorno e
            # duracao efetivamente observada. Migracao idempotente.
            incident_columns = {
                row["name"] for row in self._conn.execute("PRAGMA table_info(incidents)")
            }
            for column, ddl in (
                ("first_fail_at", "TEXT"),
                ("confirmed_at", "TEXT"),
                ("first_ok_at", "TEXT"),
                ("observed_duration_seconds", "REAL"),
                ("unobserved_seconds", "REAL"),
                ("source", "TEXT NOT NULL DEFAULT 'live'"),
                ("suppressed_by", "INTEGER"),
            ):
                if column not in incident_columns:
                    self._conn.execute(f"ALTER TABLE incidents ADD COLUMN {column} {ddl}")
            authorization_columns = self._conn.execute(
                "PRAGMA table_info(sefaz_authorizations)"
            ).fetchall()
            primary_key = [
                row["name"]
                for row in sorted(authorization_columns, key=lambda row: row["pk"])
                if row["pk"]
            ]
            if primary_key == ["event_id"]:
                # Migra a tabela introduzida antes para deduplicar dentro de
                # cada caixa, sem colidir IDs locais de emissores diferentes.
                self._conn.execute("DROP INDEX IF EXISTS idx_sefaz_auth_machine_started")
                self._conn.execute("ALTER TABLE sefaz_authorizations RENAME TO sefaz_authorizations_old")
                self._conn.execute(
                    """CREATE TABLE sefaz_authorizations (
                        event_id TEXT NOT NULL,
                        machine_name TEXT NOT NULL,
                        started_at TEXT NOT NULL,
                        completed_at TEXT NOT NULL,
                        received_at TEXT NOT NULL,
                        duration_ms INTEGER NOT NULL,
                        outcome TEXT NOT NULL,
                        PRIMARY KEY (machine_name, event_id)
                    )"""
                )
                self._conn.execute(
                    """INSERT OR IGNORE INTO sefaz_authorizations
                       (event_id, machine_name, started_at, completed_at, received_at, duration_ms, outcome)
                       SELECT event_id, machine_name, started_at, completed_at, received_at, duration_ms, outcome
                       FROM sefaz_authorizations_old"""
                )
                self._conn.execute("DROP TABLE sefaz_authorizations_old")
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sefaz_auth_machine_started "
                    "ON sefaz_authorizations (machine_name, started_at DESC)"
                )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------
    def upsert_machine(self, info: MachineInfo | None, seen_at: str | None = None) -> None:
        if info is None:
            return
        seen = seen_at or to_iso(info.collected_at) or to_iso(utc_now())
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO machines (machine_name, hostname, local_ip, agent_version,
                                      os_version, created_at, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(machine_name) DO UPDATE SET
                    hostname=excluded.hostname,
                    local_ip=excluded.local_ip,
                    agent_version=excluded.agent_version,
                    os_version=excluded.os_version,
                    last_seen=excluded.last_seen
                """,
                (
                    info.machine_name,
                    info.hostname,
                    info.local_ip,
                    info.agent_version,
                    info.os_version,
                    seen,
                    seen,
                ),
            )
            self._conn.commit()

    def insert_measurements(self, measurements: Iterable[Measurement]) -> tuple[int, int]:
        rows = [self._measurement_row(item) for item in measurements]
        if not rows:
            return 0, 0
        placeholders = ", ".join("?" for _ in MEASUREMENT_COLUMNS)
        columns = ", ".join(MEASUREMENT_COLUMNS)
        with self._lock:
            cursor = self._conn.executemany(
                f"INSERT OR IGNORE INTO measurements ({columns}) VALUES ({placeholders})", rows
            )
            self._conn.commit()
        stored = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        return stored, len(rows) - stored

    def insert_events(self, events: Iterable[EventIn]) -> tuple[int, int]:
        now = to_iso(utc_now())
        rows = [
            (
                to_iso(event.timestamp),
                event.machine_name,
                now,
                event.kind,
                event.component,
                event.severity,
                event.message,
                json.dumps(event.payload, ensure_ascii=False, default=str),
            )
            for event in events
        ]
        if not rows:
            return 0, 0
        with self._lock:
            cursor = self._conn.executemany(
                "INSERT OR IGNORE INTO events "
                "(timestamp, machine_name, received_at, kind, component, severity, message, payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            self._conn.commit()
        stored = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        return stored, len(rows) - stored

    def insert_sefaz_authorizations(
        self, authorizations: Iterable[SefazAuthorization]
    ) -> tuple[int, int]:
        now = to_iso(utc_now())
        rows = [
            (
                item.event_id,
                item.machine_name,
                to_iso(item.started_at),
                to_iso(item.completed_at),
                now,
                item.duration_ms,
                item.outcome,
            )
            for item in authorizations
        ]
        if not rows:
            return 0, 0
        with self._lock:
            cursor = self._conn.executemany(
                "INSERT OR IGNORE INTO sefaz_authorizations "
                "(event_id, machine_name, started_at, completed_at, received_at, duration_ms, outcome) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            self._conn.commit()
        stored = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        return stored, len(rows) - stored

    def sefaz_authorization_history(self, machine: str, hours: int = 24) -> list[dict[str, Any]]:
        since = to_iso(utc_now() - timedelta(hours=max(1, hours)))
        with self._lock:
            rows = self._conn.execute(
                "SELECT event_id, machine_name, started_at, completed_at, duration_ms, outcome "
                "FROM sefaz_authorizations WHERE machine_name = ? AND started_at >= ? "
                "ORDER BY started_at DESC LIMIT 5000",
                (machine.upper(), since),
            ).fetchall()
        return [dict(row) for row in rows]

    def nearest_measurement(self, machine: str, timestamp: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM measurements WHERE machine_name = ? "
                "AND ABS(julianday(timestamp) - julianday(?)) <= (5.0 / 1440.0) "
                "ORDER BY ABS(julianday(timestamp) - julianday(?)) LIMIT 1",
                (machine.upper(), timestamp, timestamp),
            ).fetchone()
        return dict(row) if row else None

    def _measurement_row(self, item: Measurement) -> tuple:
        return (
            to_iso(item.timestamp),
            item.machine_name,
            to_iso(utc_now()),
            _bool_to_int(item.gateway_ok),
            item.gateway_latency_ms,
            item.gateway_loss_pct,
            _bool_to_int(item.server_ok),
            item.server_latency_ms,
            item.server_loss_pct,
            _bool_to_int(item.internet_ok),
            item.internet_latency_ms,
            item.internet_targets_ok,
            item.internet_targets_total,
            _bool_to_int(item.dns_ok),
            item.dns_latency_ms,
            item.dns_resolver,
            _bool_to_int(item.dns_system_ok),
            _bool_to_int(item.dns_external_ok),
            json.dumps(item.resolved_ips, ensure_ascii=False),
            item.dns_error,
            _bool_to_int(item.sefaz_tcp_ok),
            item.sefaz_tcp_latency_ms,
            item.sefaz_tcp_ip,
            item.sefaz_tcp_error,
            _bool_to_int(item.sefaz_tls_ok),
            item.sefaz_tls_latency_ms,
            item.sefaz_tls_protocol,
            item.sefaz_cert_subject,
            to_iso(item.sefaz_cert_not_after),
            item.sefaz_cert_days_left,
            _bool_to_int(item.sefaz_tls_verify_ok),
            item.sefaz_tls_error,
            _bool_to_int(item.tef_connected),
            item.tef_remote_ip,
            item.tef_remote_port,
            item.tef_connections,
            item.active_wan,
            item.diagnosis,
            json.dumps(item.details, ensure_ascii=False, default=str),
        )

    def insert_wan_status(self, statuses: Iterable[WanStatus]) -> int:
        rows = [
            (
                to_iso(item.timestamp or utc_now()),
                item.wan_name,
                item.provider,
                item.status,
                item.probe,
                item.latency_ms,
                _bool_to_int(item.active_route),
                item.loss_pct,
            )
            for item in statuses
        ]
        if not rows:
            return 0
        with self._lock:
            cursor = self._conn.executemany(
                "INSERT INTO wan_status "
                "(timestamp, wan_name, provider, status, probe, latency_ms, active_route, loss_pct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            self._conn.commit()
        return cursor.rowcount or 0

    def observe_wan_status(
        self,
        wan_name: str,
        provider: str,
        status: str,
        timestamp: Any,
        probe: str | None = None,
        active_route: bool | None = None,
        confirmation_samples: int = 2,
        max_sample_gap_seconds: float = 60.0,
    ) -> str | None:
        """Persiste una transicao WAN confirmada e sua notificacao.

        Leituras desconhecidas nao mudam a ocorrencia nem a confirmacao. A
        primeira leitura valida cria apenas uma linha de base; duas leituras
        consecutivas confirmam queda/retorno e gravam a outbox na mesma
        transacao SQLite.
        """
        normalized_name = str(wan_name or "").strip().upper()
        normalized_status = str(status or "").strip().lower()
        if not normalized_name or normalized_status not in {"up", "down"}:
            return None

        stamp = to_iso(timestamp or utc_now())
        provider = str(provider or normalized_name)
        required = max(2, int(confirmation_samples))
        max_gap = max(1.0, float(max_sample_gap_seconds))
        now = to_iso(utc_now())
        active_route_value = _bool_to_int(active_route)

        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT * FROM wan_alert_state WHERE wan_name = ?",
                    (normalized_name,),
                ).fetchone()

                if row is None:
                    self._conn.execute(
                        "INSERT INTO wan_alert_state "
                        "(wan_name, provider, confirmed_status, candidate_status, "
                        "candidate_count, candidate_since, last_observed_at, updated_at) "
                        "VALUES (?, ?, 'unknown', ?, 1, ?, ?, ?)",
                        (normalized_name, provider, normalized_status, stamp, stamp, now),
                    )
                    self._conn.commit()
                    return None

                state = dict(row)
                confirmed = str(state.get("confirmed_status") or "unknown")
                candidate = state.get("candidate_status")
                candidate_count = int(state.get("candidate_count") or 0)
                candidate_since = state.get("candidate_since")

                previous_time = parse_iso(state.get("last_observed_at"))
                current_time = parse_iso(stamp)
                if previous_time and current_time:
                    gap = (current_time - previous_time).total_seconds()
                    if gap > max_gap:
                        candidate = None
                        candidate_count = 0
                        candidate_since = None

                if normalized_status == confirmed:
                    self._conn.execute(
                        "UPDATE wan_alert_state SET provider = ?, candidate_status = NULL, "
                        "candidate_count = 0, candidate_since = NULL, last_observed_at = ?, "
                        "updated_at = ? WHERE wan_name = ?",
                        (
                            state.get("provider") if confirmed == "down" else provider,
                            stamp,
                            now,
                            normalized_name,
                        ),
                    )
                    self._conn.commit()
                    return None

                if candidate != normalized_status or candidate_count <= 0:
                    candidate_count = 1
                    candidate_since = stamp
                else:
                    candidate_count += 1

                if candidate_count < required:
                    self._conn.execute(
                        "UPDATE wan_alert_state SET provider = ?, candidate_status = ?, "
                        "candidate_count = ?, candidate_since = ?, last_observed_at = ?, "
                        "updated_at = ? WHERE wan_name = ?",
                        (
                            state.get("provider") if confirmed == "down" else provider,
                            normalized_status,
                            candidate_count,
                            candidate_since,
                            stamp,
                            now,
                            normalized_name,
                        ),
                    )
                    self._conn.commit()
                    return None

                if normalized_status == "down":
                    first_fail_at = str(candidate_since or stamp)
                    dedupe_key = f"wan:{normalized_name}:{first_fail_at}:down"
                    self._conn.execute(
                        "INSERT OR IGNORE INTO wan_alert_outbox "
                        "(dedupe_key, wan_name, provider, kind, first_fail_at, "
                        "down_confirmed_at, probe, active_route, created_at) "
                        "VALUES (?, ?, ?, 'down', ?, ?, ?, ?, ?)",
                        (
                            dedupe_key,
                            normalized_name,
                            provider,
                            first_fail_at,
                            stamp,
                            probe,
                            active_route_value,
                            now,
                        ),
                    )
                    self._conn.execute(
                        "UPDATE wan_alert_state SET provider = ?, confirmed_status = 'down', "
                        "candidate_status = NULL, candidate_count = 0, candidate_since = NULL, "
                        "last_observed_at = ?, first_fail_at = ?, down_confirmed_at = ?, "
                        "down_dedupe_key = ?, updated_at = ? WHERE wan_name = ?",
                        (
                            provider,
                            stamp,
                            first_fail_at,
                            stamp,
                            dedupe_key,
                            now,
                            normalized_name,
                        ),
                    )
                    self._conn.commit()
                    return "down"

                # A WAN already confirmed down has now returned. Use the time
                # of its first successful observation for the duration.
                first_fail_at = state.get("first_fail_at")
                down_key = state.get("down_dedupe_key")
                if confirmed == "down" and first_fail_at and down_key:
                    recovered_at = str(candidate_since or stamp)
                    start = parse_iso(str(first_fail_at))
                    end = parse_iso(recovered_at)
                    duration = (
                        max(0.0, (end - start).total_seconds())
                        if start and end
                        else None
                    )
                    pending_down = self._conn.execute(
                        "SELECT id FROM wan_alert_outbox "
                        "WHERE dedupe_key = ? AND kind = 'down' AND sent_at IS NULL "
                        "AND (claimed_until IS NULL OR claimed_until < ?)",
                        (str(down_key), now),
                    ).fetchone()
                    if pending_down:
                        # If Telegram could not receive the down alert before
                        # recovery, send one accurate retrospective message.
                        self._conn.execute(
                            "UPDATE wan_alert_outbox SET kind = 'retrospective', "
                            "recovered_at = ?, recovery_confirmed_at = ?, "
                            "duration_seconds = ?, probe = COALESCE(?, probe), "
                            "active_route = COALESCE(?, active_route), "
                            "claimed_until = NULL, next_attempt_at = NULL WHERE id = ?",
                            (
                                recovered_at,
                                stamp,
                                duration,
                                probe,
                                active_route_value,
                                int(pending_down["id"]),
                            ),
                        )
                    else:
                        self._conn.execute(
                            "INSERT OR IGNORE INTO wan_alert_outbox "
                            "(dedupe_key, wan_name, provider, kind, first_fail_at, "
                            "down_confirmed_at, recovered_at, recovery_confirmed_at, "
                            "duration_seconds, probe, active_route, created_at) "
                            "VALUES (?, ?, ?, 'recovery', ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                f"{down_key}:recovery",
                                normalized_name,
                                str(state.get("provider") or provider),
                                str(first_fail_at),
                                str(state.get("down_confirmed_at") or first_fail_at),
                                recovered_at,
                                stamp,
                                duration,
                                probe,
                                active_route_value,
                                now,
                            ),
                        )

                self._conn.execute(
                    "UPDATE wan_alert_state SET provider = ?, confirmed_status = 'up', "
                    "candidate_status = NULL, candidate_count = 0, candidate_since = NULL, "
                    "last_observed_at = ?, first_fail_at = NULL, down_confirmed_at = NULL, "
                    "down_dedupe_key = NULL, updated_at = ? WHERE wan_name = ?",
                    (provider, stamp, now, normalized_name),
                )
                self._conn.commit()
                return "recovery" if confirmed == "down" else None
            except Exception:
                self._conn.rollback()
                raise

    def claim_next_wan_alert(self, lease_seconds: int = 30) -> dict[str, Any] | None:
        """Reserva uma notificacao por tempo limitado antes do envio HTTP."""
        now_dt = utc_now()
        now = to_iso(now_dt)
        lease_until = to_iso(now_dt + timedelta(seconds=max(10, int(lease_seconds))))
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT id FROM wan_alert_outbox WHERE sent_at IS NULL "
                    "AND (claimed_until IS NULL OR claimed_until < ?) "
                    "AND (next_attempt_at IS NULL OR next_attempt_at <= ?) "
                    "ORDER BY id ASC LIMIT 1",
                    (now, now),
                ).fetchone()
                if row is None:
                    self._conn.commit()
                    return None
                notification_id = int(row["id"])
                self._conn.execute(
                    "UPDATE wan_alert_outbox SET claimed_until = ? "
                    "WHERE id = ? AND sent_at IS NULL",
                    (lease_until, notification_id),
                )
                claimed = self._conn.execute(
                    "SELECT * FROM wan_alert_outbox WHERE id = ?",
                    (notification_id,),
                ).fetchone()
                self._conn.commit()
                return dict(claimed) if claimed else None
            except Exception:
                self._conn.rollback()
                raise

    def mark_wan_alert_sent(self, notification_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE wan_alert_outbox SET sent_at = ?, claimed_until = NULL, "
                "next_attempt_at = NULL WHERE id = ?",
                (to_iso(utc_now()), int(notification_id)),
            )
            self._conn.commit()

    def mark_wan_alert_failed(self, notification_id: int, error: str) -> None:
        now_dt = utc_now()
        now = to_iso(now_dt)
        retry_after = to_iso(now_dt + timedelta(seconds=30))
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                failed = self._conn.execute(
                    "SELECT * FROM wan_alert_outbox WHERE id = ? AND sent_at IS NULL",
                    (int(notification_id),),
                ).fetchone()
                if failed and failed["kind"] == "down":
                    # A recovery can be observed while the HTTP request for
                    # the down alert is in flight. If that request fails, the
                    # recovery row lets us replace both messages with one
                    # retrospective summary before retrying.
                    recovery = self._conn.execute(
                        "SELECT * FROM wan_alert_outbox WHERE dedupe_key = ? "
                        "AND kind = 'recovery' AND sent_at IS NULL "
                        "AND (claimed_until IS NULL OR claimed_until < ?)",
                        (f"{failed['dedupe_key']}:recovery", now),
                    ).fetchone()
                    if recovery:
                        self._conn.execute(
                            "UPDATE wan_alert_outbox SET kind = 'retrospective', "
                            "recovered_at = ?, recovery_confirmed_at = ?, "
                            "duration_seconds = ?, probe = COALESCE(?, probe), "
                            "active_route = COALESCE(?, active_route), "
                            "attempts = attempts + 1, last_error = ?, claimed_until = NULL, "
                            "next_attempt_at = ? WHERE id = ?",
                            (
                                recovery["recovered_at"],
                                recovery["recovery_confirmed_at"],
                                recovery["duration_seconds"],
                                recovery["probe"],
                                recovery["active_route"],
                                (error or "")[:400],
                                retry_after,
                                int(notification_id),
                            ),
                        )
                        self._conn.execute(
                            "UPDATE wan_alert_outbox SET kind = 'superseded', sent_at = ?, "
                            "last_error = 'consolidada no resumo retrospectivo' "
                            "WHERE id = ? AND sent_at IS NULL",
                            (now, int(recovery["id"])),
                        )
                        self._conn.commit()
                        return

                self._conn.execute(
                    "UPDATE wan_alert_outbox SET attempts = attempts + 1, last_error = ?, "
                    "claimed_until = NULL, next_attempt_at = ? "
                    "WHERE id = ?",
                    ((error or "")[:400], retry_after, int(notification_id)),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------
    def list_machines(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM machines ORDER BY machine_name"
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_measurements(self) -> dict[str, dict[str, Any]]:
        query = """
            SELECT m.* FROM measurements m
            JOIN (
                SELECT machine_name, MAX(timestamp) AS ts
                FROM measurements GROUP BY machine_name
            ) latest
              ON latest.machine_name = m.machine_name AND latest.ts = m.timestamp
        """
        with self._lock:
            rows = self._conn.execute(query).fetchall()
        return {row["machine_name"]: dict(row) for row in rows}

    def machine_history(self, machine: str, hours: int = 6, limit: int = 5000) -> list[dict[str, Any]]:
        since = to_iso(utc_now() - timedelta(hours=max(1, hours)))
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM measurements WHERE machine_name = ? AND timestamp >= ? "
                "ORDER BY timestamp ASC LIMIT ?",
                (machine.upper(), since, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def available_history_hours(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT MIN(timestamp) AS oldest FROM measurements"
            ).fetchone()
        oldest = parse_iso(row["oldest"]) if row and row["oldest"] else None
        if oldest is None:
            return 24
        delta = utc_now() - oldest
        return max(1, min(24 * 30, int(delta.total_seconds() // 3600) + 1))

    def recent_events(self, limit: int = 100, machine: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if machine:
                rows = self._conn.execute(
                    "SELECT * FROM events WHERE machine_name = ? "
                    "AND (component IS NULL OR component != ?) AND kind != 'tef_connection' "
                    "ORDER BY id DESC LIMIT ?",
                    (machine.upper(), C.COMPONENT_TEF, int(limit)),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM events WHERE (component IS NULL OR component != ?) "
                    "AND kind != 'tef_connection' ORDER BY id DESC LIMIT ?",
                    (C.COMPONENT_TEF, int(limit)),
                ).fetchall()
        return [dict(row) for row in rows]

    def latest_wan_status(self) -> list[dict[str, Any]]:
        query = """
            SELECT w.* FROM wan_status w
            JOIN (
                SELECT wan_name, MAX(timestamp) AS ts FROM wan_status GROUP BY wan_name
            ) latest ON latest.wan_name = w.wan_name AND latest.ts = w.timestamp
            ORDER BY w.wan_name
        """
        with self._lock:
            rows = self._conn.execute(query).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Incidentes
    # ------------------------------------------------------------------
    def open_incident(self, incident_type: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM incidents WHERE type = ? AND recovered_at IS NULL",
                (incident_type,),
            ).fetchone()
        return dict(row) if row else None

    def create_incident(
        self,
        incident_type: str,
        severity: str,
        started_at: str,
        affected_machines: list[str],
        diagnosis: str | None,
        active_wan: str | None,
    ) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO incidents (type, severity, started_at, affected_machines, "
                "diagnosis, active_wan) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    incident_type,
                    severity,
                    started_at,
                    json.dumps(sorted(set(affected_machines))),
                    diagnosis,
                    active_wan,
                ),
            )
            self._conn.commit()
            return int(cursor.lastrowid or 0)

    def update_incident(
        self,
        incident_id: int,
        affected_machines: list[str] | None = None,
        diagnosis: str | None = None,
        active_wan: str | None = None,
        severity: str | None = None,
    ) -> None:
        sets: list[str] = []
        params: list[Any] = []
        if affected_machines is not None:
            sets.append("affected_machines = ?")
            params.append(json.dumps(sorted(set(affected_machines))))
        if diagnosis is not None:
            sets.append("diagnosis = ?")
            params.append(diagnosis)
        if active_wan is not None:
            sets.append("active_wan = ?")
            params.append(active_wan)
        if severity is not None:
            sets.append("severity = ?")
            params.append(severity)
        if not sets:
            return
        params.append(incident_id)
        with self._lock:
            self._conn.execute(f"UPDATE incidents SET {', '.join(sets)} WHERE id = ?", params)
            self._conn.commit()

    def recover_incident(self, incident_id: int, recovered_at: str) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT started_at FROM incidents WHERE id = ?", (incident_id,)
            ).fetchone()
            duration = None
            if row and row["started_at"]:
                start = parse_iso(row["started_at"])
                end = parse_iso(recovered_at)
                if start and end:
                    duration = (end - start).total_seconds()
            self._conn.execute(
                "UPDATE incidents SET recovered_at = ?, duration_seconds = ? WHERE id = ?",
                (recovered_at, duration, incident_id),
            )
            self._conn.commit()

    def mark_incident_notified(self, incident_id: int, recovery: bool = False) -> None:
        column = "telegram_recovery_sent" if recovery else "telegram_sent"
        with self._lock:
            self._conn.execute(
                f"UPDATE incidents SET {column} = 1 WHERE id = ?", (incident_id,)
            )
            self._conn.commit()

    def list_incidents(
        self,
        limit: int = 50,
        only_open: bool = False,
        include_suppressed: bool = False,
    ) -> list[dict[str, Any]]:
        """Lista ocorrencias. Sintomas consolidados ficam ocultos por padrao."""
        query = "SELECT * FROM incidents WHERE type != ?"
        params: list[Any] = [C.COMPONENT_TEF]
        if only_open:
            query += " AND recovered_at IS NULL"
        if not include_suppressed:
            query += " AND suppressed_by IS NULL"
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(int(limit))
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["affected_machines"] = json.loads(item.get("affected_machines") or "[]")
            except (TypeError, ValueError):
                item["affected_machines"] = []
            item["open"] = item.get("recovered_at") is None
            out.append(item)
        return out

    def incidents_since(self, since: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM incidents WHERE type != ? AND (started_at >= ? OR recovered_at >= ?) "
                "ORDER BY started_at DESC LIMIT 500",
                (C.COMPONENT_TEF, since, since),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["affected_machines"] = json.loads(item.get("affected_machines") or "[]")
            except (TypeError, ValueError):
                item["affected_machines"] = []
            item["open"] = item.get("recovered_at") is None
            out.append(item)
        return out

    def wan_transitions(self, hours: int = 24) -> list[dict[str, Any]]:
        since = to_iso(utc_now() - timedelta(hours=max(1, hours)))
        with self._lock:
            rows = self._conn.execute(
                "SELECT timestamp, wan_name, provider, status, active_route FROM wan_status "
                "WHERE timestamp >= ? OR id IN ("
                "  SELECT id FROM wan_status old WHERE old.timestamp < ? AND old.id = ("
                "    SELECT prior.id FROM wan_status prior WHERE prior.wan_name = old.wan_name "
                "    AND prior.timestamp < ? ORDER BY prior.timestamp DESC LIMIT 1"
                "  )"
                ") ORDER BY wan_name, timestamp",
                (since, since, since),
            ).fetchall()
        previous: dict[str, tuple[str, Any]] = {}
        changes: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            name = str(item["wan_name"])
            current = (str(item.get("status") or "unknown"), item.get("active_route"))
            old = previous.get(name)
            if item["timestamp"] >= since and old is not None and current != old[1]:
                changes.append(
                    {
                        **item,
                        "previous_status": old[1][0],
                        "previous_active_route": old[1][1],
                    }
                )
            previous[name] = (str(item["timestamp"]), current)
        return changes

    # ------------------------------------------------------------------
    # Maquina de estados por componente
    # ------------------------------------------------------------------
    def get_component_states(self) -> dict[tuple[str, str], dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM component_state").fetchall()
        return {(row["machine_name"], row["component"]): dict(row) for row in rows}

    def set_component_state(
        self,
        machine_name: str,
        component: str,
        last_status: bool | None,
        consecutive_fail: int,
        consecutive_ok: int,
        last_change_at: str | None,
        last_check_at: str | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO component_state
                    (machine_name, component, last_status, consecutive_fail,
                     consecutive_ok, last_change_at, last_check_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(machine_name, component) DO UPDATE SET
                    last_status=excluded.last_status,
                    consecutive_fail=excluded.consecutive_fail,
                    consecutive_ok=excluded.consecutive_ok,
                    last_change_at=excluded.last_change_at,
                    last_check_at=excluded.last_check_at,
                    updated_at=excluded.updated_at
                """,
                (
                    machine_name,
                    component,
                    _bool_to_int(last_status),
                    consecutive_fail,
                    consecutive_ok,
                    last_change_at,
                    last_check_at,
                    to_iso(utc_now()),
                ),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Metricas e manutencao
    # ------------------------------------------------------------------
    def counts(self) -> dict[str, int]:
        with self._lock:
            machines = self._conn.execute("SELECT COUNT(*) AS c FROM machines").fetchone()["c"]
            measurements = self._conn.execute("SELECT COUNT(*) AS c FROM measurements").fetchone()["c"]
            events = self._conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
            incidents = self._conn.execute(
                "SELECT COUNT(*) AS c FROM incidents WHERE type != ?", (C.COMPONENT_TEF,)
            ).fetchone()["c"]
            open_incidents = self._conn.execute(
                "SELECT COUNT(*) AS c FROM incidents WHERE type != ? AND recovered_at IS NULL",
                (C.COMPONENT_TEF,),
            ).fetchone()["c"]
        return {
            "machines": int(machines),
            "measurements": int(measurements),
            "events": int(events),
            "incidents": int(incidents),
            "open_incidents": int(open_incidents),
        }

    def availability(self, machine: str, hours: int = 24) -> dict[str, float]:
        """Disponibilidade percentual por componente na janela informada."""
        since = to_iso(utc_now() - timedelta(hours=max(1, hours)))
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    COUNT(gateway_ok) AS gateway_total,
                    SUM(CASE WHEN gateway_ok = 1 THEN 1 ELSE 0 END) AS gateway_ok,
                    COUNT(server_ok) AS server_total,
                    SUM(CASE WHEN server_ok = 1 THEN 1 ELSE 0 END) AS server_ok,
                    COUNT(internet_ok) AS internet_total,
                    SUM(CASE WHEN internet_ok = 1 THEN 1 ELSE 0 END) AS internet_ok,
                    COUNT(dns_ok) AS dns_total,
                    SUM(CASE WHEN dns_ok = 1 THEN 1 ELSE 0 END) AS dns_ok,
                    COUNT(sefaz_tcp_ok) AS sefaz_tcp_total,
                    SUM(CASE WHEN sefaz_tcp_ok = 1 THEN 1 ELSE 0 END) AS sefaz_tcp_ok,
                    COUNT(sefaz_tls_ok) AS sefaz_tls_total,
                    SUM(CASE WHEN sefaz_tls_ok = 1 THEN 1 ELSE 0 END) AS sefaz_tls_ok
                FROM measurements
                WHERE machine_name = ? AND timestamp >= ?
                """,
                (machine.upper(), since),
            ).fetchone()
        result: dict[str, float] = {}
        for component in ("gateway", "server", "internet", "dns", "sefaz_tcp", "sefaz_tls"):
            total = int(row[f"{component}_total"] or 0)
            if total:
                result[f"{component}_ok"] = round(
                    100.0 * int(row[f"{component}_ok"] or 0) / total, 3
                )
        return result

    def purge_old(self, retention_days: int) -> dict[str, int]:
        if retention_days <= 0:
            return {}
        cutoff = to_iso(utc_now() - timedelta(days=retention_days))
        removed: dict[str, int] = {}
        with self._lock:
            for table in ("measurements", "events", "wan_status"):
                cursor = self._conn.execute(f"DELETE FROM {table} WHERE timestamp < ?", (cutoff,))
                removed[table] = cursor.rowcount or 0
            cursor = self._conn.execute(
                "DELETE FROM wan_alert_outbox WHERE sent_at IS NOT NULL AND created_at < ?",
                (cutoff,),
            )
            removed["wan_alert_outbox"] = cursor.rowcount or 0
            self._conn.execute(
                "DELETE FROM incidents WHERE recovered_at IS NOT NULL AND recovered_at < ?",
                (cutoff,),
            )
            self._conn.execute("DELETE FROM sefaz_authorizations WHERE started_at < ?", (cutoff,))
            self._conn.commit()
        return removed

    def backup(self, destination: Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(str(destination))
            try:
                self._conn.backup(target)
            finally:
                target.close()
        return destination

    # ------------------------------------------------------------------
    # Ocorrencias: estado observado por (maquina, componente)
    # ------------------------------------------------------------------
    def get_occurrence_states(self) -> dict[tuple[str, str], dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM occurrence_state").fetchall()
        return {(row["machine_name"], row["component"]): dict(row) for row in rows}

    def set_occurrence_state(
        self,
        machine_name: str,
        component: str,
        *,
        consecutive_fail: int,
        consecutive_ok: int,
        first_fail_at: str | None,
        first_ok_at: str | None,
        last_observed_at: str | None,
        incident_id: int | None,
        unobserved_seconds: float,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO occurrence_state
                    (machine_name, component, consecutive_fail, consecutive_ok,
                     first_fail_at, first_ok_at, last_observed_at, incident_id,
                     unobserved_seconds, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(machine_name, component) DO UPDATE SET
                    consecutive_fail=excluded.consecutive_fail,
                    consecutive_ok=excluded.consecutive_ok,
                    first_fail_at=excluded.first_fail_at,
                    first_ok_at=excluded.first_ok_at,
                    last_observed_at=excluded.last_observed_at,
                    incident_id=excluded.incident_id,
                    unobserved_seconds=excluded.unobserved_seconds,
                    updated_at=excluded.updated_at
                """,
                (
                    machine_name,
                    component,
                    consecutive_fail,
                    consecutive_ok,
                    first_fail_at,
                    first_ok_at,
                    last_observed_at,
                    incident_id,
                    float(unobserved_seconds or 0.0),
                    to_iso(utc_now()),
                ),
            )
            self._conn.commit()

    def reset_occurrence_state(self, machine_name: str, component: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM occurrence_state WHERE machine_name = ? AND component = ?",
                (machine_name, component),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Ocorrencias: atributos observados do incidente
    # ------------------------------------------------------------------
    def incident_by_id(self, incident_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM incidents WHERE id = ?", (incident_id,)
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["affected_machines"] = json.loads(item.get("affected_machines") or "[]")
        except (TypeError, ValueError):
            item["affected_machines"] = []
        item["open"] = item.get("recovered_at") is None
        return item

    def set_incident_observation(
        self,
        incident_id: int,
        *,
        first_fail_at: str | None = None,
        confirmed_at: str | None = None,
        source: str | None = None,
    ) -> None:
        sets: list[str] = []
        params: list[Any] = []
        if first_fail_at is not None:
            sets.append("first_fail_at = CASE WHEN first_fail_at IS NULL OR first_fail_at > ? THEN ? ELSE first_fail_at END")
            params.extend([first_fail_at, first_fail_at])
        if confirmed_at is not None:
            sets.append("confirmed_at = ?")
            params.append(confirmed_at)
        if source is not None:
            sets.append("source = ?")
            params.append(source)
        if not sets:
            return
        params.append(incident_id)
        with self._lock:
            self._conn.execute(f"UPDATE incidents SET {', '.join(sets)} WHERE id = ?", params)
            self._conn.commit()

    def set_incident_suppressed(self, incident_id: int, root_incident_id: int | None) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE incidents SET suppressed_by = ? WHERE id = ?",
                (root_incident_id, incident_id),
            )
            self._conn.commit()

    def finalize_incident(
        self,
        incident_id: int,
        *,
        recovered_at: str,
        first_ok_at: str | None,
        observed_duration_seconds: float | None,
        unobserved_seconds: float | None,
    ) -> None:
        """Encerra a ocorrencia registrando a duracao efetivamente observada."""
        with self._lock:
            self._conn.execute(
                "UPDATE incidents SET recovered_at = ?, first_ok_at = ?, "
                "observed_duration_seconds = ?, unobserved_seconds = ?, "
                "duration_seconds = ? WHERE id = ?",
                (
                    recovered_at,
                    first_ok_at,
                    observed_duration_seconds,
                    unobserved_seconds,
                    observed_duration_seconds,
                    incident_id,
                ),
            )
            self._conn.commit()

    def set_incident_machines(self, incident_id: int, machines: list[str]) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE incidents SET affected_machines = ? WHERE id = ?",
                (json.dumps(sorted(set(machines))), incident_id),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Outbox de notificacoes (persistente, deduplicado)
    # ------------------------------------------------------------------
    def enqueue_notification(self, dedupe_key: str, incident_id: int, kind: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO notifications (dedupe_key, incident_id, kind, created_at) "
                "VALUES (?, ?, ?, ?)",
                (dedupe_key, incident_id, kind, to_iso(utc_now())),
            )
            self._conn.commit()
            return bool(cursor.rowcount)

    def pending_notification_rows(self, limit: int = 50) -> list[dict[str, Any]]:
        query = """
            SELECT n.id AS notification_id, n.dedupe_key, n.incident_id, n.kind AS notification_kind,
                   n.attempts, n.created_at AS notification_created_at,
                   i.*
            FROM notifications n
            JOIN incidents i ON i.id = n.incident_id
            WHERE n.sent_at IS NULL
            ORDER BY n.id ASC
            LIMIT ?
        """
        with self._lock:
            rows = self._conn.execute(query, (int(limit),)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["affected_machines"] = json.loads(item.get("affected_machines") or "[]")
            except (TypeError, ValueError):
                item["affected_machines"] = []
            item["open"] = item.get("recovered_at") is None
            out.append(item)
        return out

    def mark_notification_sent(self, notification_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE notifications SET sent_at = ? WHERE id = ?",
                (to_iso(utc_now()), int(notification_id)),
            )
            self._conn.commit()

    def mark_notification_failed(self, notification_id: int, error: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE notifications SET attempts = attempts + 1, last_error = ? WHERE id = ?",
                ((error or "")[:400], int(notification_id)),
            )
            self._conn.commit()

    def cancel_notification(self, dedupe_key: str, reason: str = "cancelada") -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE notifications SET sent_at = ?, last_error = ? "
                "WHERE dedupe_key = ? AND sent_at IS NULL",
                (to_iso(utc_now()), reason[:400], dedupe_key),
            )
            self._conn.commit()

    def notification_summary(self) -> dict[str, int]:
        with self._lock:
            pending = self._conn.execute(
                "SELECT COUNT(*) AS c FROM notifications WHERE sent_at IS NULL"
            ).fetchone()["c"]
            total = self._conn.execute("SELECT COUNT(*) AS c FROM notifications").fetchone()["c"]
        return {"pending": int(pending), "total": int(total)}

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.commit()
            finally:
                self._conn.close()
