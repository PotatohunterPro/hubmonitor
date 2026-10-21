"""Testes do motor de ocorrencias.

Cobrem a lacuna apontada no pedido: uma falha que comeca e termina
durante a perda de comunicacao precisa ser reconstruida depois, com os
horarios originais, sem virar alerta de falha atual e sem duplicar.
"""

from __future__ import annotations

from datetime import timedelta

from server.database.db import Database
from server.services import occurrences as occ
from server.services.occurrences import Observation, OccurrenceEngine
from shared import constants as C
from shared.timeutil import parse_iso, to_iso, utc_now

BASE = utc_now().replace(microsecond=0) - timedelta(hours=2)


def at(seconds: int):
    return BASE + timedelta(seconds=seconds)


def sample(engine: OccurrenceEngine, component: str, ok: bool, seconds: int, source: str = "replay"):
    return engine.observe([Observation("CAIXA02", component, at(seconds), ok, source)])


def make_engine(db: Database, settings) -> OccurrenceEngine:
    return OccurrenceEngine(db, settings)


def test_primeira_falha_e_persistida_antes_da_confirmacao(db: Database, settings):
    engine = make_engine(db, settings)
    sample(engine, C.COMPONENT_INTERNET, False, 0)

    state = db.get_occurrence_states()[("CAIXA02", C.COMPONENT_INTERNET)]
    assert state["consecutive_fail"] == 1
    assert state["first_fail_at"] == to_iso(at(0))
    assert state["incident_id"] is None  # ainda nao confirmada
    assert db.open_incident(C.COMPONENT_INTERNET) is None


def test_tres_falhas_confirmam_a_ocorrencia(db: Database, settings):
    engine = make_engine(db, settings)
    for seconds in (0, 10, 20):
        sample(engine, C.COMPONENT_INTERNET, False, seconds)

    incident = db.open_incident(C.COMPONENT_INTERNET)
    assert incident is not None
    assert incident["first_fail_at"] == to_iso(at(0))
    assert incident["confirmed_at"] == to_iso(at(20))
    assert incident["source"] == "replay"


def test_ocorrencia_completa_na_perda_de_comunicacao_e_reconstruida(db: Database, settings):
    """Falha que comeca e termina offline: ocorrencia fechada + retrospectiva."""
    engine = make_engine(db, settings)
    samples = [(0, False), (10, False), (20, False), (40, True), (60, True), (80, True)]
    for seconds, ok in samples:
        sample(engine, C.COMPONENT_INTERNET, ok, seconds)

    incident = db.incident_by_id(1)
    assert incident is not None
    assert incident["recovered_at"] == to_iso(at(80))
    assert incident["first_fail_at"] == to_iso(at(0))
    assert incident["observed_duration_seconds"] == 80.0
    assert db.open_incident(C.COMPONENT_INTERNET) is None

    plans = [occ.plan_notification(row) for row in db.pending_notification_rows()]
    assert plans, "deveria haver notificacao pendente"
    assert set(plans) == {"retrospective"}


def test_replay_e_idempotente(db: Database, settings):
    engine = make_engine(db, settings)
    samples = [(0, False), (10, False), (20, False), (40, True), (60, True), (80, True)]
    for seconds, ok in samples:
        sample(engine, C.COMPONENT_INTERNET, ok, seconds)
    for seconds, ok in samples:
        sample(engine, C.COMPONENT_INTERNET, ok, seconds)

    assert len(db.list_incidents(include_suppressed=True)) == 1
    assert db.notification_summary()["total"] == 2  # open + recovery


def test_lacuna_nao_entra_na_duracao(db: Database, settings):
    """Sem observacao por 5 min: o periodo e lacuna, nao duracao de falha."""
    engine = make_engine(db, settings)
    for seconds in (0, 10, 20):
        sample(engine, C.COMPONENT_SEFAZ_TCP, False, seconds)
    # agente desligado por 300 s
    for offset in (320, 330, 340):
        sample(engine, C.COMPONENT_SEFAZ_TCP, True, offset)

    incident = db.incident_by_id(1)
    assert incident["unobserved_seconds"] >= 300
    assert incident["observed_duration_seconds"] is not None
    assert incident["observed_duration_seconds"] < 340
    assert incident["observed_duration_seconds"] == 340 - 300


def test_internet_consolida_dns_e_sefaz(db: Database, settings):
    """Queda de internet nao gera tres alertas."""
    engine = make_engine(db, settings)
    timeline = [
        ("internet", False), ("dns", False), ("sefaz_tcp", False),
        ("internet", False), ("dns", False), ("sefaz_tcp", False),
        ("internet", False), ("dns", False), ("sefaz_tcp", False),
    ]
    observations = []
    for index, (component, ok) in enumerate(timeline):
        observations.append(Observation("CAIXA02", component, at(index * 10), ok, "replay"))
    engine.observe(observations)

    visible = db.list_incidents(only_open=True)
    assert len(visible) == 1
    assert visible[0]["type"] == C.COMPONENT_INTERNET

    hidden = db.list_incidents(only_open=True, include_suppressed=True)
    assert len(hidden) == 3
    suppressed = [item for item in hidden if item["type"] != C.COMPONENT_INTERNET]
    assert all(item["suppressed_by"] == visible[0]["id"] for item in suppressed)


def test_sintoma_consolidado_nao_gera_notificacao(db: Database, settings):
    engine = make_engine(db, settings)
    observations = []
    for index in range(3):
        for component in ("internet", "dns", "sefaz_tcp"):
            observations.append(Observation("CAIXA02", component, at(index * 10), False, "replay"))
    engine.observe(observations)
    engine.consolidate()

    # Sintomas consolidados tem a notificacao cancelada na hora, portanto
    # nao sobra nada pendente para eles: apenas a causa raiz permanece.
    pending = db.pending_notification_rows()
    assert [row["type"] for row in pending] == [C.COMPONENT_INTERNET]
    assert occ.plan_notification(pending[0]) == "open"

    suppressed = [
        item for item in db.list_incidents(only_open=True, include_suppressed=True)
        if item["suppressed_by"]
    ]
    assert len(suppressed) == 2


def test_notificacao_duplicada_nao_e_enfileirada(db: Database, settings):
    assert db.enqueue_notification("1:open", 1, "open") is True
    assert db.enqueue_notification("1:open", 1, "open") is False
    assert db.notification_summary()["total"] == 1


def test_plano_de_notificacao_por_estado():
    assert occ.plan_notification({"notification_kind": "open", "recovered_at": None}) == "open"
    assert occ.plan_notification({"notification_kind": "open", "recovered_at": "x"}) == "retrospective"
    assert occ.plan_notification({"notification_kind": "recovery", "telegram_sent": 0}) == "retrospective"
    assert occ.plan_notification({"notification_kind": "recovery", "telegram_sent": 1}) == "recovery"
    assert occ.plan_notification({"notification_kind": "open", "suppressed_by": 3}) == "skip"

def test_internet_derrubada_nao_gera_alerta_de_dns_nem_de_sefaz(db: Database, settings):
    """C1 do roteiro: uma causa, um alerta."""
    engine = make_engine(db, settings)
    observacoes = []
    for passo in range(3):
        for componente in (
            C.COMPONENT_INTERNET,
            C.COMPONENT_DNS,
            C.COMPONENT_SEFAZ_TCP,
            C.COMPONENT_SEFAZ_TLS,
        ):
            observacoes.append(
                Observation("CAIXA02", componente, at(passo * 10), False, "replay")
            )
    engine.observe(observacoes)
    engine.consolidate()

    abertas = db.list_incidents(only_open=True)
    assert [item["type"] for item in abertas] == [C.COMPONENT_INTERNET]

    todas = db.list_incidents(include_suppressed=True, limit=50)
    suprimidas = [item for item in todas if item["type"] != C.COMPONENT_INTERNET]
    assert suprimidas, "as demais deveriam existir como sintoma"
    assert all(item["suppressed_by"] for item in suprimidas)
