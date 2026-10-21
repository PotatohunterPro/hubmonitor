from __future__ import annotations

import sqlite3

from shared.schemas import SefazAuthorization
from server.database.db import Database
from shared.timeutil import utc_now


def test_migrates_authorization_event_id_to_machine_scoped_deduplication(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """CREATE TABLE sefaz_authorizations (
            event_id TEXT PRIMARY KEY,
            machine_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            received_at TEXT NOT NULL,
            duration_ms INTEGER NOT NULL,
            outcome TEXT NOT NULL
        );
        CREATE INDEX idx_sefaz_auth_machine_started
            ON sefaz_authorizations (machine_name, started_at DESC);
        INSERT INTO sefaz_authorizations VALUES (
            'local-1', 'CAIXA01', '2026-10-12T12:00:00.000Z',
            '2026-10-12T12:00:01.000Z', '2026-10-12T12:00:02.000Z', 1000, 'authorized'
        );"""
    )
    connection.commit()
    connection.close()

    database = Database(path)
    try:
        original = database.sefaz_authorization_history("CAIXA01", hours=720)
        assert len(original) == 1

        now = utc_now()
        other_machine = SefazAuthorization(
            event_id="local-1",
            machine_name="CAIXA02",
            started_at=now,
            completed_at=now,
            duration_ms=0,
            outcome="unknown",
        )
        assert database.insert_sefaz_authorizations([other_machine]) == (1, 0)
        assert len(database.sefaz_authorization_history("CAIXA02", hours=720)) == 1
    finally:
        database.close()
