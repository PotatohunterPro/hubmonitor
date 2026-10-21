"""Testes de persistencia e deduplicacao."""

from __future__ import annotations

from server.database.db import Database
from shared.schemas import EventIn, MachineInfo, Measurement
from shared.timeutil import utc_now


def test_medicao_duplicada_e_ignorada(db: Database):
    stamp = utc_now()
    item = Measurement(machine_name="CAIXA02", timestamp=stamp, gateway_ok=True)
    stored, duplicates = db.insert_measurements([item])
    assert (stored, duplicates) == (1, 0)

    stored, duplicates = db.insert_measurements([item])
    assert (stored, duplicates) == (0, 1)
    assert db.counts()["measurements"] == 1


def test_lote_reenviado_nao_duplica(db: Database):
    stamp = utc_now()
    batch = [Measurement(machine_name="CAIXA02", timestamp=stamp, gateway_ok=True)]
    db.insert_measurements(batch)
    # Reenvio identico, como faria a fila local do PDV
    stored, duplicates = db.insert_measurements(batch)
    assert stored == 0 and duplicates == 1


def test_ultima_medicao_por_maquina(db: Database):
    from datetime import timedelta

    base = utc_now()
    db.insert_measurements(
        [
            Measurement(machine_name="CAIXA02", timestamp=base, internet_latency_ms=10.0),
            Measurement(
                machine_name="CAIXA02", timestamp=base + timedelta(seconds=5), internet_latency_ms=20.0
            ),
            Measurement(machine_name="CAIXA01", timestamp=base, internet_latency_ms=30.0),
        ]
    )
    latest = db.latest_measurements()
    assert set(latest) == {"CAIXA01", "CAIXA02"}
    assert latest["CAIXA02"]["internet_latency_ms"] == 20.0


def test_upsert_maquina_atualiza_last_seen(db: Database):
    info = MachineInfo(machine_name="caixa02", hostname="PDV-02", local_ip="192.168.0.100")
    db.upsert_machine(info)
    rows = db.list_machines()
    assert len(rows) == 1
    assert rows[0]["machine_name"] == "CAIXA02"
    assert rows[0]["local_ip"] == "192.168.0.100"

    info.local_ip = "192.168.0.101"
    db.upsert_machine(info)
    assert db.list_machines()[0]["local_ip"] == "192.168.0.101"


def test_evento_duplicado_e_ignorado(db: Database):
    stamp = utc_now()
    event = EventIn(
        machine_name="CAIXA02", timestamp=stamp, kind="state_change", component="gateway"
    )
    assert db.insert_events([event]) == (1, 0)
    assert db.insert_events([event]) == (0, 1)


def test_retencao_remove_dados_antigos(db: Database):
    from datetime import timedelta

    old = utc_now() - timedelta(days=120)
    db.insert_measurements([Measurement(machine_name="CAIXA02", timestamp=old, gateway_ok=True)])
    db.insert_measurements([Measurement(machine_name="CAIXA02", timestamp=utc_now(), gateway_ok=True)])
    removed = db.purge_old(90)
    assert removed["measurements"] == 1
    assert db.counts()["measurements"] == 1


def test_disponibilidade_percentual(db: Database):
    from datetime import timedelta

    base = utc_now()
    for index in range(4):
        db.insert_measurements(
            [
                Measurement(
                    machine_name="CAIXA02",
                    timestamp=base + timedelta(seconds=index),
                    sefaz_tcp_ok=index != 0,
                )
            ]
        )
    availability = db.availability("CAIXA02", hours=1)
    assert availability["sefaz_tcp_ok"] == 75.0


def test_disponibilidade_ignora_amostras_desconhecidas_no_denominador(db: Database):
    from datetime import timedelta

    base = utc_now()
    db.insert_measurements(
        [
            Measurement(machine_name="CAIXA02", timestamp=base, sefaz_tls_ok=True),
            Measurement(machine_name="CAIXA02", timestamp=base + timedelta(seconds=1), sefaz_tls_ok=False),
            Measurement(machine_name="CAIXA02", timestamp=base + timedelta(seconds=2)),
        ]
    )
    availability = db.availability("CAIXA02", hours=1)
    assert availability["sefaz_tls_ok"] == 50.0
    assert "gateway_ok" not in availability
