"""Testes do comando de backup (usado pela tarefa diaria)."""

from __future__ import annotations

import sqlite3
import time

from server.database.db import Database
from server.main import run_backup
from shared.schemas import MachineInfo


def test_backup_gera_arquivo_sqlite_valido(settings):
    db = Database(settings.db_path)
    db.upsert_machine(MachineInfo(machine_name="CAIXA02", hostname="PDV-02"))
    db.close()

    assert run_backup(settings) == 0

    backups = sorted((settings.data_dir / "backup").glob("bertolo-*.db"))
    assert len(backups) == 1

    connection = sqlite3.connect(backups[0])
    try:
        tabelas = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        maquinas = connection.execute("SELECT COUNT(*) FROM machines").fetchone()[0]
    finally:
        connection.close()

    assert {"machines", "measurements", "incidents"} <= tabelas
    assert maquinas >= 1


def test_backup_mantem_no_maximo_14_arquivos(settings):
    backup_dir = settings.data_dir / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for index in range(20):
        antigo = backup_dir / f"bertolo-2020010{index % 9}-000000-{index:02d}.db"
        antigo.write_bytes(b"antigo")
        # Garante ordem de modificacao distinta.
        timestamp = time.time() - (100 - index)
        import os

        os.utime(antigo, (timestamp, timestamp))

    assert run_backup(settings) == 0

    restantes = sorted(backup_dir.glob("bertolo-*.db"))
    assert len(restantes) == 14


def test_backup_nao_quebra_sem_banco_previo(settings):
    # Database cria o schema ao abrir; o comando nao pode falhar por isso.
    assert run_backup(settings) == 0
    assert list((settings.data_dir / "backup").glob("bertolo-*.db"))
