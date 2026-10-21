"""Continuidade apos reiniciar o processo (motor e agente).

Criterio de aceite: "reiniciar o agente nao corrompe o historico" e uma
ocorrencia em andamento nao pode ser perdida nem duplicada quando o
servico reinicia no meio dela.
"""

from __future__ import annotations

from datetime import timedelta

from agent.config import AgentSettings
from server.database.db import Database
from server.services import occurrences as occ
from server.services.occurrences import Observation, OccurrenceEngine
from shared import constants as C
from shared.connection_file import build_connection, write_connection
from shared.timeutil import parse_iso, to_iso, utc_now

BASE = utc_now().replace(microsecond=0) - timedelta(hours=2)
CERT = "-----BEGIN CERTIFICATE-----\nMIIBfake\n-----END CERTIFICATE-----\n"


def at(seconds: int):
    return BASE + timedelta(seconds=seconds)


def feed(engine: OccurrenceEngine, component: str, samples) -> None:
    engine.observe(
        [Observation("CAIXA02", component, at(seconds), ok, "replay") for seconds, ok in samples]
    )


def test_primeira_falha_sobrevive_ao_reinicio(db: Database, settings):
    feed(OccurrenceEngine(db, settings), C.COMPONENT_INTERNET, [(0, False), (10, False)])

    # reinicio: nova instancia, mesmo banco
    engine = OccurrenceEngine(db, settings)
    feed(engine, C.COMPONENT_INTERNET, [(20, False)])

    incident = db.open_incident(C.COMPONENT_INTERNET)
    assert incident is not None
    assert incident["first_fail_at"] == to_iso(at(0))
    assert incident["confirmed_at"] == to_iso(at(20))


def test_recuperacao_funciona_apos_reinicio(db: Database, settings):
    feed(OccurrenceEngine(db, settings), C.COMPONENT_SEFAZ_TCP, [(0, False), (10, False), (20, False)])
    assert db.open_incident(C.COMPONENT_SEFAZ_TCP) is not None

    engine = OccurrenceEngine(db, settings)
    feed(engine, C.COMPONENT_SEFAZ_TCP, [(40, True), (60, True), (80, True)])

    assert db.open_incident(C.COMPONENT_SEFAZ_TCP) is None
    incident = db.incident_by_id(1)
    assert incident["recovered_at"] == to_iso(at(80))
    assert incident["observed_duration_seconds"] == 80.0


def test_lacuna_atravessa_reinicio(db: Database, settings):
    feed(OccurrenceEngine(db, settings), C.COMPONENT_INTERNET, [(0, False), (10, False), (20, False)])

    # processo fica 5 minutos parado e volta
    engine = OccurrenceEngine(db, settings)
    feed(engine, C.COMPONENT_INTERNET, [(320, True), (330, True), (340, True)])

    incident = db.incident_by_id(1)
    assert incident["unobserved_seconds"] >= 300
    assert incident["observed_duration_seconds"] == 340 - 300


def test_reinicio_nao_duplica_ocorrencia(db: Database, settings):
    for _ in range(3):
        feed(OccurrenceEngine(db, settings), C.COMPONENT_INTERNET, [(0, False)])
    # o mesmo instante nao avanca o contador em uma nova instancia
    feed(OccurrenceEngine(db, settings), C.COMPONENT_INTERNET, [(0, False)])

    assert len(db.list_incidents(include_suppressed=True)) == 0


def test_novo_ciclo_apos_recuperacao_gera_nova_ocorrencia(db: Database, settings):
    engine = OccurrenceEngine(db, settings)
    feed(engine, C.COMPONENT_INTERNET, [(0, False), (10, False), (20, False)])
    feed(engine, C.COMPONENT_INTERNET, [(40, True), (60, True), (80, True)])
    assert db.open_incident(C.COMPONENT_INTERNET) is None

    # nova falha depois da recuperacao, em um processo novo
    engine = OccurrenceEngine(db, settings)
    feed(engine, C.COMPONENT_INTERNET, [(100, False), (110, False), (120, False)])

    incident = db.open_incident(C.COMPONENT_INTERNET)
    assert incident is not None
    assert incident["first_fail_at"] == to_iso(at(100))
    assert incident["id"] != 1


def test_arquivo_de_conexao_corrompido_nao_derruba_o_agente(tmp_path, monkeypatch):
    ruim = tmp_path / "connection.json"
    ruim.write_text("{ isto nao e json", encoding="utf-8")
    monkeypatch.setenv("CONNECTION_FILE", str(ruim))
    monkeypatch.delenv("SERVER_URL", raising=False)

    settings = AgentSettings.from_env()

    assert settings.server_url  # caiu no padrao, sem excecao
    assert settings.connection_file is None


def test_arquivo_de_conexao_adulterado_nao_derruba_o_agente(tmp_path, monkeypatch):
    caminho = tmp_path / "connection.json"
    write_connection(
        caminho,
        build_connection(
            store_name="Loja",
            base_url="https://192.168.0.110:8443",
            agent_token="agente-" + "x" * 40,
            ca_certificate_pem=CERT,
            server_name="SERVIDOR",
        ),
    )
    data = caminho.read_text(encoding="utf-8").replace("192.168.0.110", "10.0.0.9")
    caminho.write_text(data, encoding="utf-8")
    monkeypatch.setenv("CONNECTION_FILE", str(caminho))
    monkeypatch.setenv("SERVER_URL", "https://10.0.0.5:8443")

    settings = AgentSettings.from_env()

    # Fingerprint invalido: ignora o arquivo e usa o ambiente.
    assert settings.server_url == "https://10.0.0.5:8443"
    assert settings.connection_file is None
