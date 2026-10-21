"""Testes dos endpoints de destino fiscal (UF + documento)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from server.main import create_app

LOCAL = ("127.0.0.1", 50000)


def make_client(settings, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("STORE_NAME=LOJA MODELO\n", encoding="utf-8")
    settings.env_file = env_path
    app = create_app(settings)
    client = TestClient(app, client=LOCAL)
    client.__enter__()
    return client, env_path


def admin_client(settings, tmp_path):
    client, env_path = make_client(settings, tmp_path)
    response = client.post("/api/v1/admin/setup", json={"password": "senha-muito-forte-123"})
    assert response.status_code == 200, response.text
    return client, env_path


def base_payload(**overrides):
    payload = {
        "store_name": "Mercado Bertolo",
        "local_subnet": "192.168.0.0/24",
        "telegram_enabled": False,
        "mikrotik_enabled": False,
        "fiscal_uf": "SP",
        "fiscal_document": "nfce",
        "sefaz_host": "nfce.fazenda.sp.gov.br",
        "sefaz_port": 443,
        "fiscal_confirmed": True,
    }
    payload.update(overrides)
    return payload


def test_opcoes_fiscais_trazem_as_27_ufs(settings, tmp_path):
    client, _ = admin_client(settings, tmp_path)
    try:
        response = client.get("/api/v1/admin/fiscal/options")
        assert response.status_code == 200
        body = response.json()
        assert len(body["ufs"]) == 27
        assert body["documents"]["nfe"].startswith("NF-e")
    finally:
        client.__exit__(None, None, None)


def test_salva_e_devolve_o_destino_fiscal(settings, tmp_path):
    client, env_path = admin_client(settings, tmp_path)
    try:
        put = client.put("/api/v1/admin/settings", json=base_payload())
        assert put.status_code == 200, put.text

        data = client.get("/api/v1/admin/settings").json()
        assert data["fiscal_uf"] == "SP"
        assert data["fiscal_document"] == "nfce"
        assert data["sefaz_host"] == "nfce.fazenda.sp.gov.br"
        assert data["fiscal_configured"] is True

        saved = env_path.read_text(encoding="utf-8")
        assert "SEFAZ_HOST" in saved
        assert "FISCAL_UF" in saved
    finally:
        client.__exit__(None, None, None)


def test_recusa_uf_invalida(settings, tmp_path):
    client, _ = admin_client(settings, tmp_path)
    try:
        put = client.put("/api/v1/admin/settings", json=base_payload(fiscal_uf="XX"))
        assert put.status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_recusa_endereco_de_loopback(settings, tmp_path):
    client, _ = admin_client(settings, tmp_path)
    try:
        put = client.put(
            "/api/v1/admin/settings", json=base_payload(sefaz_host="localhost")
        )
        assert put.status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_teste_fiscal_recusa_endereco_invalido_sem_rede(settings, tmp_path):
    client, _ = admin_client(settings, tmp_path)
    try:
        response = client.post("/api/v1/admin/fiscal/test", json={"host": "127.0.0.1"})
        assert response.status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_nao_altera_o_fiscal_quando_o_campo_vem_vazio(settings, tmp_path):
    client, _ = admin_client(settings, tmp_path)
    try:
        client.put("/api/v1/admin/settings", json=base_payload())
        client.put(
            "/api/v1/admin/settings",
            json=base_payload(sefaz_host="", fiscal_uf="", fiscal_confirmed=False),
        )
        data = client.get("/api/v1/admin/settings").json()
        # O destino configurado permanece: nao limpamos por acidente.
        assert data["sefaz_host"] == "nfce.fazenda.sp.gov.br"
    finally:
        client.__exit__(None, None, None)

def test_mudanca_do_destino_fiscal_reinicia_o_agente_local(settings, tmp_path, monkeypatch):
    from server.services import config_store

    chamadas = []

    def falso_restart():
        chamadas.append(True)
        return True

    monkeypatch.setattr(config_store, "restart_local_agent", falso_restart)

    client, _ = admin_client(settings, tmp_path)
    try:
        response = client.put("/api/v1/admin/settings", json=base_payload())
        assert response.status_code == 200, response.text
        assert chamadas == [True]
    finally:
        client.__exit__(None, None, None)


def test_salvar_sem_mudar_o_destino_nao_reinicia_de_novo(settings, tmp_path, monkeypatch):
    from server.services import config_store

    chamadas = []
    monkeypatch.setattr(
        config_store, "restart_local_agent", lambda: chamadas.append(True) or True
    )

    client, _ = admin_client(settings, tmp_path)
    try:
        assert client.put("/api/v1/admin/settings", json=base_payload()).status_code == 200
        assert len(chamadas) == 1
        # Mesmos valores: nao ha por que reiniciar o agente outra vez.
        assert client.put("/api/v1/admin/settings", json=base_payload()).status_code == 200
        assert len(chamadas) == 1
    finally:
        client.__exit__(None, None, None)


def test_reinicio_do_agente_e_noop_fora_do_windows(monkeypatch):
    from server.services import config_store

    monkeypatch.setattr(config_store.os, "name", "posix")
    chamadas = []
    monkeypatch.setattr(
        config_store.subprocess, "run", lambda *args, **kwargs: chamadas.append(args)
    )

    assert config_store.restart_local_agent() is False
    assert chamadas == []
