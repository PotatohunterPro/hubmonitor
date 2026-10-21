"""Leitor opcional de JSONL do emissor; persiste somente campos permitidos."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.queue.local_queue import LocalQueue
from shared.schemas import SefazAuthorization
from shared.timeutil import to_iso, utc_now

MAX_LINE_BYTES = 64 * 1024
MAX_READ_BYTES = 2 * 1024 * 1024
OUTCOMES = {
    "authorized": "authorized", "autorizado": "authorized", "autorizada": "authorized",
    "approved": "authorized", "100": "authorized", "rejected": "rejected", "rejeitado": "rejected",
    "rejeitada": "rejected", "denied": "rejected", "error": "error", "erro": "error",
    "failed": "error", "falha": "error", "timeout": "timeout", "timed_out": "timeout",
    "tempo_esgotado": "timeout", "unknown": "unknown", "desconhecido": "unknown",
}


def parse_authorization_record(raw: bytes | str, machine_name: str) -> SefazAuthorization | None:
    """Extrai o resumo autorizado e ignora qualquer outro campo da linha."""
    if isinstance(raw, bytes):
        if len(raw) > MAX_LINE_BYTES:
            return None
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if len(raw.encode("utf-8", errors="ignore")) > MAX_LINE_BYTES:
        return None
    try:
        record = json.loads(raw)
        if not isinstance(record, dict):
            return None
        duration = record.get("duration_ms")
        event_id = record.get("event_id")
        if not isinstance(event_id, str):
            return None
        if isinstance(duration, bool) or not isinstance(duration, int):
            return None
        outcome = OUTCOMES.get(str(record.get("outcome", "")).strip().lower(), "unknown")
        return SefazAuthorization(
            event_id=event_id,
            machine_name=machine_name,
            started_at=_parse_datetime(record.get("started_at")),
            completed_at=_parse_datetime(record.get("completed_at")),
            duration_ms=duration,
            outcome=outcome,
        )
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp ausente")
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp precisa informar fuso")
    return parsed


class SefazAuthorizationLogReader:
    """Faz tail do log configurado sem armazenar linhas brutas."""

    def __init__(
        self,
        path: Path,
        machine_name: str,
        queue: LocalQueue,
        logger: logging.Logger | None = None,
    ) -> None:
        self.path = Path(path)
        self.machine_name = machine_name
        self.queue = queue
        self.log = logger or logging.getLogger("agent.sefaz_authorization_log")
        path_hash = hashlib.sha256(str(self.path.resolve()).encode("utf-8")).hexdigest()[:16]
        self.checkpoint_key = f"sefaz_authorization_log:{path_hash}"
        self.valid_seen_key = f"{self.checkpoint_key}:valid_seen"
        self.valid_seen = queue.get_value(self.valid_seen_key) == "1"
        self.records_total = 0
        self.invalid_total = 0
        self.last_read_at: str | None = None
        self.last_error: str | None = None

    def poll(self) -> int:
        try:
            if not self.path.is_file():
                self.last_error = "arquivo nao encontrado"
                return 0
            stat = self.path.stat()
            identity = f"{stat.st_dev}:{stat.st_ino}"
            previous = self.queue.get_value(self.checkpoint_key)
            if previous is None:
                # O piloto comeca a observar novas emissoes, sem ler historico fiscal.
                offset = stat.st_size
            else:
                try:
                    checkpoint = json.loads(previous)
                except (TypeError, ValueError):
                    checkpoint = {}
                if checkpoint.get("identity") != identity:
                    # Arquivo novo/rotacionado: nao importar historico que ja
                    # existia antes de o agente observar este arquivo.
                    offset = stat.st_size
                else:
                    offset = int(checkpoint.get("offset", 0))
                    if offset > stat.st_size:
                        # Truncamento detectado. Recomece do fim para evitar
                        # reprocessar linhas antigas mantidas pelo emissor.
                        offset = stat.st_size

            extracted: list[SefazAuthorization] = []
            consumed = 0
            with self.path.open("rb") as stream:
                stream.seek(offset)
                while consumed < MAX_READ_BYTES:
                    line = stream.readline(MAX_LINE_BYTES + 1)
                    if not line:
                        break
                    if len(line) > MAX_LINE_BYTES:
                        while line and not line.endswith(b"\n"):
                            line = stream.readline(MAX_LINE_BYTES + 1)
                        consumed = stream.tell() - offset
                        self.invalid_total += 1
                        continue
                    if not line.endswith(b"\n"):
                        break
                    item = parse_authorization_record(line, self.machine_name)
                    if item is None:
                        self.invalid_total += 1
                    else:
                        extracted.append(item)
                    consumed = stream.tell() - offset

            # Repeticao apos crash e segura: o servidor deduplica por event_id.
            for item in extracted:
                self.queue.enqueue("sefaz_authorization", item.model_dump(mode="json"))
            if extracted:
                self.queue.set_value(self.valid_seen_key, "1")
                self.valid_seen = True
            self.queue.set_value(
                self.checkpoint_key,
                json.dumps({"identity": identity, "offset": offset + consumed}),
            )
            self.records_total += len(extracted)
            self.last_read_at = to_iso(utc_now())
            self.last_error = None
            return len(extracted)
        except Exception as exc:  # noqa: BLE001 - o leitor opcional nao pode derrubar o agente
            self.last_error = type(exc).__name__
            self.log.warning("Falha ao ler o log de autorizacao (%s)", type(exc).__name__)
            return 0

    def status(self) -> dict[str, Any]:
        return {
            "configured": True,
            "available": self.last_error is None and self.valid_seen,
            "last_read_at": self.last_read_at,
            "records_total": self.records_total,
            "invalid_total": self.invalid_total,
            "last_error": self.last_error,
        }
