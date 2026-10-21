"""Testes de autenticacao do agente na API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from server.main import create_app

LOCAL = ("127.0.0.1", 50000)
TOKEN = "test-agent-token"  # definido no fixture settings


def payload():
    return {
        "machine": {"machine_name": "CAIXA02", "hostname": "PDV-02"},
        "measurements": [{"machine_name": "CAIXA02", "internet_ok": True}],
    }


def client_for(settings):
    return TestClient(create_app(settings), client=LOCAL)


def test_medicoes_sem_credencial_sao_recusadas(settings):
    with client_for(settings) as client:
        assert client.post("/api/v1/measurements", json=payload()).status_code == 401


def test_medicoes_com_credencial_errada_sao_recusadas(settings):
    with client_for(settings) as client:
        response = client.post(
            "/api/v1/measurements",
            json=payload(),
            headers={"Authorization": "Bearer outra-credencial"},
        )
        assert response.status_code == 401


def test_medicoes_com_credencial_correta_sao_aceitas(settings):
    with client_for(settings) as client:
        response = client.post(
            "/api/v1/measurements",
            json=payload(),
            headers={"Authorization": "Bearer " + TOKEN},
        )
        assert response.status_code == 200
        assert response.json()["stored"] == 1


def test_eventos_tambem_exigem_credencial(settings):
    with client_for(settings) as client:
        body = {
            "machine": {"machine_name": "CAIXA02"},
            "events": [{"machine_name": "CAIXA02", "kind": "info", "message": "teste"}],
        }
        assert client.post("/api/v1/events", json=body).status_code == 401


def test_status_publico_dentro_da_rede(settings):
    """O painel da rede local continua acessivel sem credencial de agente."""
    with client_for(settings) as client:
        assert client.get("/api/v1/status").status_code == 200
