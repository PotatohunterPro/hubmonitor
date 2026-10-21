"""Fila local SQLite - plano secao 8.

Se o servidor estiver indisponivel:
  1. continuar monitorando;
  2. armazenar metricas/eventos localmente;
  3. marcar como pendente;
  4. reenviar quando o servidor voltar;
  5. preservar o timestamp original.

O item so e removido da fila depois de aceito pelo servidor, portanto
uma queda de energia no PDV nao perde dado.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from shared.timeutil import to_iso, utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    last_try_at TEXT,
    last_error  TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_kind ON outbox (kind, id);
CREATE TABLE IF NOT EXISTS queue_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass(slots=True)
class QueueStats:
    measurements: int = 0
    events: int = 0
    authorizations: int = 0
    total: int = 0
    oldest_age_seconds: float | None = None
    sent_total: int = 0
    send_failures: int = 0
    max_rows: int = 0
    trimmed: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "measurements": self.measurements,
            "events": self.events,
            "authorizations": self.authorizations,
            "total": self.total,
            "oldest_age_seconds": self.oldest_age_seconds,
            "sent_total": self.sent_total,
            "send_failures": self.send_failures,
            "max_rows": self.max_rows,
            "trimmed": self.trimmed,
        }


class LocalQueue:
    """Fila persistente com uma conexao SQLite em modo WAL."""

    def __init__(self, path: Path, max_rows: int = 200_000, logger: logging.Logger | None = None) -> None:
        self.path = Path(path)
        self.max_rows = int(max_rows)
        self.log = logger or logging.getLogger("agent.queue")
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()
        self._trimmed = 0

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------
    def enqueue(self, kind: str, payload: dict[str, Any]) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO outbox (kind, payload, created_at) VALUES (?, ?, ?)",
                (kind, json.dumps(payload, ensure_ascii=False, default=str), to_iso(utc_now())),
            )
            self._conn.commit()
            return int(cursor.lastrowid or 0)

    def enqueue_many(self, items: Iterable[tuple[str, dict[str, Any]]]) -> int:
        rows = [
            (kind, json.dumps(payload, ensure_ascii=False, default=str), to_iso(utc_now()))
            for kind, payload in items
        ]
        if not rows:
            return 0
        with self._lock:
            self._conn.executemany(
                "INSERT INTO outbox (kind, payload, created_at) VALUES (?, ?, ?)", rows
            )
            self._conn.commit()
        return len(rows)

    def delete(self, ids: Iterable[int]) -> int:
        ids = list(ids)
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with self._lock:
            cursor = self._conn.execute(
                f"DELETE FROM outbox WHERE id IN ({placeholders})", ids
            )
            self._conn.commit()
            return cursor.rowcount

    def mark_failed(self, ids: Iterable[int], error: str) -> int:
        ids = list(ids)
        if not ids:
            return 0
        message = (error or "")[:500]
        placeholders = ",".join("?" for _ in ids)
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE outbox SET attempts = attempts + 1, last_try_at = ?, last_error = ? "
                f"WHERE id IN ({placeholders})",
                [to_iso(utc_now()), message, *ids],
            )
            self._conn.commit()
            return cursor.rowcount

    def bump_counter(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO queue_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = CAST(CAST(value AS INTEGER) + ? AS TEXT)",
                (key, str(amount), amount),
            )
            self._conn.commit()

    def get_counter(self, key: str) -> int:
        with self._lock:
            row = self._conn.execute("SELECT value FROM queue_meta WHERE key = ?", (key,)).fetchone()
        try:
            return int(row["value"]) if row else 0
        except (TypeError, ValueError):
            return 0

    def get_value(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM queue_meta WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def set_value(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO queue_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------
    def pending(self, kind: str, limit: int = 200) -> list[sqlite3.Row]:
        with self._lock:
            return list(
                self._conn.execute(
                    "SELECT id, payload, created_at, attempts FROM outbox "
                    "WHERE kind = ? ORDER BY id ASC LIMIT ?",
                    (kind, int(limit)),
                ).fetchall()
            )

    def counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT kind, COUNT(*) AS total FROM outbox GROUP BY kind"
            ).fetchall()
        return {row["kind"]: int(row["total"]) for row in rows}

    def oldest_age(self) -> float | None:
        with self._lock:
            row = self._conn.execute("SELECT MIN(created_at) AS oldest FROM outbox").fetchone()
        if not row or not row["oldest"]:
            return None
        from shared.timeutil import parse_iso

        parsed = parse_iso(row["oldest"])
        if parsed is None:
            return None
        return max(0.0, time.time() - parsed.timestamp())

    def stats(self) -> QueueStats:
        counts = self.counts()
        total = sum(counts.values())
        return QueueStats(
            measurements=counts.get("measurement", 0),
            events=counts.get("event", 0),
            authorizations=counts.get("sefaz_authorization", 0),
            total=total,
            oldest_age_seconds=self.oldest_age(),
            sent_total=self.get_counter("sent_total"),
            send_failures=self.get_counter("send_failures"),
            max_rows=self.max_rows,
            trimmed=self._trimmed,
        )

    # ------------------------------------------------------------------
    # Manutencao
    # ------------------------------------------------------------------
    def trim(self) -> int:
        """Remove os itens mais antigos se a fila passar do limite.

        Protecao contra disco cheio. Só age quando a fila realmente
        cresceu muito (servidor fora do ar por muito tempo).
        """
        total = sum(self.counts().values())
        excess = total - self.max_rows
        if excess <= 0:
            return 0

        # Medicoes sao descartaveis (o valor esta no historico agregado).
        # Eventos de falha e recuperacao sao a prova da ocorrencia e so
        # sao removidos se ainda estivermos acima do limite.
        removed = 0
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM outbox WHERE id IN ("
                "SELECT id FROM outbox WHERE kind = 'measurement' ORDER BY id ASC LIMIT ?)",
                (excess,),
            )
            removed += cursor.rowcount or 0
            self._conn.commit()

            remaining = excess - removed
            if remaining > 0:
                cursor = self._conn.execute(
                    "DELETE FROM outbox WHERE id IN ("
                    "SELECT id FROM outbox WHERE kind = 'event' ORDER BY id ASC LIMIT ?)",
                    (remaining,),
                )
                removed += cursor.rowcount or 0
                self._conn.commit()

        self._trimmed += removed
        if removed:
            self.log.warning(
                "Fila local acima do limite: %d itens descartados (medicoes primeiro)", removed
            )
        return removed

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.commit()
            finally:
                self._conn.close()
