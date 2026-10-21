"""Testes do download do arquivo de conexao pela interface administrativa."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from server.config import ServerSettings
from server.main import create_app
from server.tls import generate_local_certificate
from shared.connection_file import read_connection

LOCAL = ("127.0.0.1", 50000)


def make_client(tmp_path, monkeypatch, **overrides):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "b.db"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("AGENT_INGEST_TOKEN", "token-de-loja-1234567890")
    monkeypatch.setenv("STORE_NAME", "Mercado Bertolo")
    # Cookie de sessao sem Secure, para o TestClient enviar em http://.
    monkeypatch.setenv("SERVER_ALLOW_HTTP", "true")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)

    settings = ServerSettings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    cert, key, _ca = generate_local_certificate(
        settings.data_dir / "certs", "SERVIDOR", "192.168.0.110"
    )
    settings.tls_cert_file = cert
    settings.tls_key_file = key
    env_file = tmp_path / ".env"
    env_file.write_text("STORE_NAME=Mercado Bertolo\n", encoding="utf-8")
    settings.env_file = env_file

    client = TestClient(create_app(settings), client=LOCAL)
    client.__enter__()
    return client


def admin(client) -> None:
    response = client.post("/api/v1/admin/setup", json={"password": "senha-muito-forte-123"})
    assert response.status_code == 200, response.text


def test_download_exige_administrador(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    try:
        response = client.get("/api/v1/admin/connection-file")
        assert response.status_code in (401, 403)
    finally:
        client.__exit__(None, None, None)


def test_download_entrega_arquivo_valido(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    try:
        admin(client)
        response = client.get("/api/v1/admin/connection-file")
        assert response.status_code == 200, response.text
        assert "attachment" in response.headers["content-disposition"]
        assert ".hubconn" in response.headers["content-disposition"]
        assert "no-store" in response.headers.get("cache-control", "")

        destino = tmp_path / "baixado.hubconn"
        destino.write_bytes(response.content)
        data = read_connection(destino)

        assert data["base_url"].startswith("https://")
        assert data["agent_token"] == "token-de-loja-1234567890"
        assert "BEGIN CERTIFICATE" in data["ca_certificate_pem"]
        assert "PRIVATE KEY" not in response.text
        assert "TELEGRAM" not in response.text.upper()
    finally:
        client.__exit__(None, None, None)


def test_download_inclui_o_destino_fiscal(tmp_path, monkeypatch):
    client = make_client(
        tmp_path,
        monkeypatch,
        FISCAL_UF="SP",
        FISCAL_DOCUMENT="nfce",
        SEFAZ_HOST="nfce.fazenda.sp.gov.br",
        SEFAZ_PORT="443",
    )
    try:
        admin(client)
        response = client.get("/api/v1/admin/connection-file")
        destino = tmp_path / "baixado.hubconn"
        destino.write_bytes(response.content)
        data = read_connection(destino)
        assert data["fiscal"]["uf"] == "SP"
        assert data["fiscal"]["host"] == "nfce.fazenda.sp.gov.br"
    finally:
        client.__exit__(None, None, None)


def test_download_sem_credencial_do_agente_falha_cedo(tmp_path, monkeypatch):
    # Token curto: a API sobe, mas o arquivo nao pode ser gerado.
    client = make_client(tmp_path, monkeypatch, AGENT_INGEST_TOKEN="curto")
    try:
        admin(client)
        response = client.get("/api/v1/admin/connection-file")
        assert response.status_code == 409
        assert "credencial" in json.dumps(response.json()).lower()
    finally:
        client.__exit__(None, None, None)
