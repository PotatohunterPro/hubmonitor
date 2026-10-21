"""Testes da deteccao de incidentes - plano secoes 15 e 20."""

from __future__ import annotations

from server.database.db import Database
from server.services.incidents import IncidentManager
from shared import constants as C
from tests.conftest import status


def run_cycle(manager: IncidentManager, statuses: dict, wans: list | None = None):
    return manager.evaluate(statuses, wans or [])


def test_duas_falhas_nao_abrem_incidente(db: Database, settings):
    manager = IncidentManager(db, settings)
    for _ in range(2):
        events = run_cycle(manager, {"CAIXA02": status("CAIXA02", sefaz_tcp_ok=False)})
    assert not [event for event in events if event.action == "open"]
    assert db.open_incident(C.COMPONENT_SEFAZ_TCP) is None


def test_tres_falhas_abrem_incidente(db: Database, settings):
    manager = IncidentManager(db, settings)
    events = []
    for _ in range(3):
        events = run_cycle(manager, {"CAIXA02": status("CAIXA02", sefaz_tcp_ok=False)})
    abertos = [event for event in events if event.action == "open"]
    assert len(abertos) == 1
    incident = db.open_incident(C.COMPONENT_SEFAZ_TCP)
    assert incident is not None
    assert incident["affected_machines"] == '["CAIXA02"]'


def test_tres_sucessos_recuperam_incidente(db: Database, settings):
    manager = IncidentManager(db, settings)
    for _ in range(3):
        run_cycle(manager, {"CAIXA02": status("CAIXA02", sefaz_tcp_ok=False)})
    assert db.open_incident(C.COMPONENT_SEFAZ_TCP) is not None

    events = []
    for _ in range(3):
        events = run_cycle(manager, {"CAIXA02": status("CAIXA02")})
    assert [event for event in events if event.action == "recover"]
    assert db.open_incident(C.COMPONENT_SEFAZ_TCP) is None


def test_dois_sucessos_ainda_nao_recuperam(db: Database, settings):
    manager = IncidentManager(db, settings)
    for _ in range(3):
        run_cycle(manager, {"CAIXA02": status("CAIXA02", sefaz_tcp_ok=False)})
    for _ in range(2):
        run_cycle(manager, {"CAIXA02": status("CAIXA02")})
    assert db.open_incident(C.COMPONENT_SEFAZ_TCP) is not None


def test_falha_simultanea_gera_um_unico_incidente_agregado(db: Database, settings):
    manager = IncidentManager(db, settings)
    for _ in range(3):
        statuses = {
            name: status(name, sefaz_tcp_ok=False)
            for name in ("CAIXA01", "CAIXA02", "CAIXA03")
        }
        run_cycle(manager, statuses)

    incidents = db.list_incidents(only_open=True)
    assert len(incidents) == 1
    assert incidents[0]["affected_machines"] == ["CAIXA01", "CAIXA02", "CAIXA03"]
    assert "origem final não foi confirmada" in (incidents[0]["diagnosis"] or "")


def test_maquina_offline_nao_gera_incidente(db: Database, settings):
    manager = IncidentManager(db, settings)
    offline = {"CAIXA02": status("CAIXA02", online=False, sefaz_tcp_ok=False)}
    for _ in range(5):
        events = run_cycle(manager, offline)
    assert not [event for event in events if event.action == "open"]


def test_tef_fica_fora_dos_incidentes_ativos(db: Database, settings):
    manager = IncidentManager(db, settings)
    for _ in range(3):
        run_cycle(manager, {"CAIXA02": status("CAIXA02", sefaz_tcp_ok=False, tef_connected=False)})
    abertos = db.list_incidents(only_open=True)
    tipos = sorted(item["type"] for item in abertos)
    assert tipos == [C.COMPONENT_SEFAZ_TCP]


def test_notificacao_pendente_aparece_uma_vez(db: Database, settings):
    manager = IncidentManager(db, settings)
    for _ in range(3):
        run_cycle(manager, {"CAIXA02": status("CAIXA02", internet_ok=False)})
    pendentes = manager.pending_notifications()
    assert len(pendentes) == 1
    action, incident = pendentes[0]
    assert action == "open"
    db.mark_incident_notified(incident["id"], recovery=False)
    assert manager.pending_notifications() == []


def test_snapshots_repetidos_nao_avancam_contador(db: Database, settings):
    manager = IncidentManager(db, settings)
    repeated = {"CAIXA02": status("CAIXA02", sefaz_tcp_ok=False)}
    for _ in range(5):
        run_cycle(manager, repeated)
    state = db.get_occurrence_states()[("CAIXA02", C.COMPONENT_SEFAZ_TCP)]
    assert state["consecutive_fail"] == 1
    assert db.open_incident(C.COMPONENT_SEFAZ_TCP) is None


def test_replay_preserva_primeira_falha_e_horarios_originais(db: Database, settings):
    """Dado antigo reconstroi a ocorrencia com os horarios originais."""
    from datetime import timedelta

    from shared.timeutil import to_iso, utc_now

    manager = IncidentManager(db, settings)
    stale_time = utc_now() - timedelta(minutes=10)
    for index in range(4):
        checked_at = to_iso(stale_time + timedelta(seconds=index * 5))
        old = status("CAIXA02", sefaz_tcp_ok=False)
        old["check_timestamps"] = {component: checked_at for component in C.COMPONENTS}
        run_cycle(manager, {"CAIXA02": old})

    incident = db.open_incident(C.COMPONENT_SEFAZ_TCP)
    assert incident is not None
    assert incident["source"] == "replay"
    assert incident["first_fail_at"] == to_iso(stale_time)
    assert incident["confirmed_at"] == to_iso(stale_time + timedelta(seconds=10))

    # A falha persiste: a ocorrencia segue aberta e um novo ciclo nao duplica
    current = status("CAIXA02", sefaz_tcp_ok=False)
    events = run_cycle(manager, {"CAIXA02": current})
    assert not [event for event in events if event.action == "open"]
    assert len([item for item in db.list_incidents(only_open=True)]) == 1
