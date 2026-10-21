"""Testes da API - plano secao 10."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.main import create_app
from shared.timeutil import to_iso, utc_now

AUTH = {"Authorization": "Bearer test-agent-token"}


def make_payload(machine: str = "CAIXA02", **overrides) -> dict:
    measurement = {
        "machine_name": machine,
        "timestamp": to_iso(utc_now()),
        "gateway_ok": True,
        "gateway_latency_ms": 1.2,
        "server_ok": True,
        "internet_ok": True,
        "dns_ok": True,
        "sefaz_tcp_ok": True,
        "sefaz_tls_ok": True,
        "tef_connected": False,
    }
    measurement.update(overrides)
    return {
        "machine": {
            "machine_name": machine,
            "hostname": "PDV-02",
            "local_ip": "192.168.0.100",
            "agent_version": "0.1.0",
            "os_version": "Windows 10",
        },
        "measurements": [measurement],
    }


def test_health_responde(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["database"] == "ok"


def test_ingestao_de_medicoes_e_deduplicacao(settings):
    with TestClient(create_app(settings)) as client:
        payload = make_payload()
        first = client.post("/api/v1/measurements", json=payload, headers=AUTH)
        assert first.status_code == 200
        assert first.json()["stored"] == 1

        # Reenvio da fila local: mesmo timestamp, nao pode duplicar
        second = client.post("/api/v1/measurements", json=payload, headers=AUTH)
        assert second.json()["stored"] == 0
        assert second.json()["duplicates"] == 1


def test_ingestao_exige_token(settings):
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/v1/measurements", json=make_payload())
        assert response.status_code == 401
        auth_response = client.post(
            "/api/v1/sefaz-authorizations", json={"authorizations": [{"event_id": "no-token"}]}
        )
        assert auth_response.status_code == 401


def test_servidor_nao_inicia_sem_token_de_ingestao(settings):
    settings.agent_ingest_token = ""
    with pytest.raises(RuntimeError, match="AGENT_INGEST_TOKEN"):
        with TestClient(create_app(settings)):
            pass


def test_diagnostico_e_calculado_no_ingest(settings):
    with TestClient(create_app(settings)) as client:
        client.post("/api/v1/measurements", json=make_payload(sefaz_tcp_ok=False), headers=AUTH)
        machines = client.get("/api/v1/machines").json()
        assert machines[0]["diagnosis"] == "CAMINHO / SEFAZ"


def test_status_traz_maquinas_e_wans(settings):
    with TestClient(create_app(settings)) as client:
        client.post("/api/v1/measurements", json=make_payload(), headers=AUTH)
        body = client.get("/api/v1/status").json()
        assert body["store_name"]
        assert len(body["machines"]) == 1
        assert body["machines"][0]["machine_name"] == "CAIXA02"
        assert body["wans"] == []
        assert body["open_incidents"] == []


def test_eventos_sao_armazenados(settings):
    with TestClient(create_app(settings)) as client:
        payload = {
            "machine": {"machine_name": "CAIXA02"},
            "events": [
                {
                    "machine_name": "CAIXA02",
                    "timestamp": to_iso(utc_now()),
                    "kind": "state_change",
                    "component": "gateway",
                    "severity": "critical",
                    "message": "Rede local em falha",
                }
            ],
        }
        assert client.post("/api/v1/events", json=payload, headers=AUTH).json()["stored"] == 1
        events = client.get("/api/v1/events").json()
        assert events[0]["component"] == "gateway"


def test_historico_e_disponibilidade(settings):
    with TestClient(create_app(settings)) as client:
        client.post("/api/v1/measurements", json=make_payload(), headers=AUTH)
        history = client.get("/api/v1/machines/CAIXA02/history?hours=1").json()
        assert history["count"] == 1
        assert history["availability"]["internet_ok"] == 100.0


def test_dashboard_responde_html(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "SAÚDE OPERACIONAL DA LOJA" in response.text or "Saúde dos caixas" in response.text


def test_autorizacao_e_deduplicada_sem_persistir_conteudo_fiscal(settings):
    now = utc_now()
    timestamp = to_iso(now)
    checks = {
        component: {"checked_at": timestamp, "ok": True, "latency_ms": 2.5}
        for component in ("gateway", "internet", "sefaz_tcp", "sefaz_tls")
    }
    measurement = make_payload(
        details={
            "checks": checks,
            "sefaz_authorization_log": {"configured": True, "available": True},
        }
    )
    authorization = {
        "event_id": "evt-1001",
        "machine_name": "CAIXA02",
        "started_at": to_iso(now),
        "completed_at": to_iso(now),
        "duration_ms": 6200,
        "outcome": "authorized",
        "xml": "XML-NAO-PERSISTIR",
        "consumer_name": "CLIENTE-NAO-PERSISTIR",
        "access_key": "CHAVE-NAO-PERSISTIR",
    }
    payload = {
        "machine": {"machine_name": "CAIXA02"},
        "authorizations": [authorization],
        "raw_fiscal_payload": "NAO-PERSISTIR",
    }
    with TestClient(create_app(settings)) as client:
        client.post("/api/v1/measurements", json=measurement, headers=AUTH)
        first = client.post("/api/v1/sefaz-authorizations", json=payload, headers=AUTH)
        second = client.post("/api/v1/sefaz-authorizations", json=payload, headers=AUTH)
        assert first.json()["stored"] == 1
        assert second.json()["duplicates"] == 1
        history = client.get("/api/v1/machines/CAIXA02/sefaz-authorizations?hours=24").json()
        assert history["available"] is True
        assert history["summary"]["p50_ms"] == 6200.0
        assert history["summary"]["p95_ms"] == 6200.0
        assert history["authorizations"][0]["diagnosis"] == "demora após a conexão ou no emissor/SEFAZ"
        serialized = str(history)
        assert "XML-NAO-PERSISTIR" not in serialized
        assert "CLIENTE-NAO-PERSISTIR" not in serialized
        assert "CHAVE-NAO-PERSISTIR" not in serialized
        rows = client.app.state.ctx.db.sefaz_authorization_history("CAIXA02")
        assert set(rows[0]) == {
            "event_id", "machine_name", "started_at", "completed_at", "duration_ms", "outcome"
        }


def test_medicao_de_autorizacao_sem_log_e_indisponivel(settings):
    with TestClient(create_app(settings)) as client:
        result = client.get("/api/v1/machines/CAIXA02/sefaz-authorizations").json()
        assert result["available"] is False
        assert result["summary"]["p50_ms"] is None


def test_tef_antigo_nao_volta_ao_historico_ativo_nem_ao_painel(settings):
    with TestClient(create_app(settings)) as client:
        client.post(
            "/api/v1/measurements", json=make_payload(tef_connected=True), headers=AUTH
        )
        stored = client.app.state.ctx.db.latest_measurements()["CAIXA02"]
        assert stored["tef_connected"] is None
        history = client.get("/api/v1/machines/CAIXA02/history?hours=1").json()
        assert "tef_connected" not in history["measurements"][0]

        events = {
            "machine": {"machine_name": "CAIXA02"},
            "events": [
                {
                    "machine_name": "CAIXA02",
                    "kind": "tef_connection",
                    "component": "tef",
                    "message": "legado",
                },
                {
                    "machine_name": "CAIXA02",
                    "kind": "info",
                    "component": "gateway",
                    "message": "rede",
                },
            ],
        }
        response = client.post("/api/v1/events", json=events, headers=AUTH)
        assert response.json()["stored"] == 1
        assert response.json()["rejected"] == 1
        assert [event["component"] for event in client.get("/api/v1/events").json()] == ["gateway"]

        client.app.state.ctx.db.create_incident(
            "tef", "warning", to_iso(utc_now()), ["CAIXA02"], "legado", None
        )
        status = client.get("/api/v1/status").json()
        assert status["incidents"] == []
        assert status["open_incidents"] == []
        assert client.get("/api/v1/incidents?only_open=true").json() == []


def test_event_ids_locais_nao_colidem_entre_caixas(settings):
    timestamp = to_iso(utc_now())
    authorization = {
        "event_id": "issuer-event-1",
        "machine_name": "CAIXA01",
        "started_at": timestamp,
        "completed_at": timestamp,
        "duration_ms": 1000,
        "outcome": "authorized",
    }
    with TestClient(create_app(settings)) as client:
        first = client.post(
            "/api/v1/sefaz-authorizations",
            json={"machine": {"machine_name": "CAIXA01"}, "authorizations": [authorization]},
            headers=AUTH,
        )
        authorization["machine_name"] = "CAIXA02"
        second = client.post(
            "/api/v1/sefaz-authorizations",
            json={"machine": {"machine_name": "CAIXA02"}, "authorizations": [authorization]},
            headers=AUTH,
        )
        assert first.json()["stored"] == 1
        assert second.json()["stored"] == 1
