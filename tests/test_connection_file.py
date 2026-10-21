"""Testes do arquivo de conexão da loja e da prioridade da fila."""

from __future__ import annotations

import json

import pytest

from agent.config import AgentSettings
from agent.queue.local_queue import LocalQueue
from shared.connection_file import (
    ConnectionFileError,
    build_connection,
    read_connection,
    write_connection,
)

CERT = "-----BEGIN CERTIFICATE-----\nMIIBfake\n-----END CERTIFICATE-----\n"
TOKEN = "agente-" + "x" * 40


def make(**overrides):
    data = {
        "store_name": "Mercado Bertolo",
        "base_url": "https://192.168.0.110:8443",
        "agent_token": TOKEN,
        "ca_certificate_pem": CERT,
        "server_name": "SERVIDOR-BERTOLO",
    }
    data.update(overrides)
    return build_connection(**data)


def test_ida_e_volta(tmp_path):
    path = write_connection(tmp_path / "loja.hubconn", make())
    data = read_connection(path)
    assert data["base_url"] == "https://192.168.0.110:8443"
    assert data["agent_token"] == TOKEN
    assert data["version"] == 1
    assert len(data["fingerprint"]) == 64


def test_endereco_http_e_recusado():
    with pytest.raises(ConnectionFileError):
        make(base_url="http://192.168.0.110:8000")


def test_token_curto_e_recusado():
    with pytest.raises(ConnectionFileError):
        make(agent_token="curto")


def test_certificado_ausente_e_recusado():
    with pytest.raises(ConnectionFileError):
        make(ca_certificate_pem="nada")


def test_arquivo_adulterado_e_recusado(tmp_path):
    path = tmp_path / "loja.hubconn"
    write_connection(path, make())
    data = json.loads(path.read_text(encoding="utf-8"))
    data["agent_token"] = "invasor-" + "y" * 40
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConnectionFileError, match="Fingerprint"):
        read_connection(path)


def test_chave_privada_nunca_e_aceita(tmp_path):
    path = tmp_path / "ruim.hubconn"
    data = make()
    data["ca_certificate_pem"] = "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConnectionFileError, match="nunca deve ser compartilhada"):
        read_connection(path)


def test_token_telegram_nunca_e_aceito(tmp_path):
    path = tmp_path / "ruim.hubconn"
    path.write_text('{"TELEGRAM_BOT_TOKEN": "123"}', encoding="utf-8")
    with pytest.raises(ConnectionFileError, match="nunca deve ser compartilhada"):
        read_connection(path)


def test_leitura_tolera_bom(tmp_path):
    path = tmp_path / "loja.hubconn"
    write_connection(path, make())
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert read_connection(path)["agent_token"] == TOKEN


def test_agente_usa_o_arquivo_de_conexao(tmp_path, monkeypatch):
    path = write_connection(tmp_path / "loja.hubconn", make())
    monkeypatch.setenv("CONNECTION_FILE", str(path))
    monkeypatch.delenv("SERVER_URL", raising=False)
    monkeypatch.delenv("AGENT_INGEST_TOKEN", raising=False)

    settings = AgentSettings.from_env()
    assert settings.server_url == "https://192.168.0.110:8443"
    assert settings.agent_ingest_token == TOKEN
    assert settings.server_ca_file is not None
    assert settings.server_ca_file.is_file()
    assert settings.connection_file == path
    assert "BEGIN CERTIFICATE" in settings.server_ca_file.read_text(encoding="utf-8")


def test_agente_ignora_arquivo_invalido(tmp_path, monkeypatch):
    path = tmp_path / "loja.hubconn"
    path.write_text("nao e json", encoding="utf-8")
    monkeypatch.setenv("CONNECTION_FILE", str(path))
    monkeypatch.setenv("SERVER_URL", "https://10.0.0.5:8443")
    settings = AgentSettings.from_env()
    assert settings.server_url == "https://10.0.0.5:8443"


def test_fila_preserva_eventos_ao_atingir_o_limite(tmp_path):
    queue = LocalQueue(tmp_path / "fila.db", max_rows=5)
    for index in range(10):
        queue.enqueue("measurement", {"n": index})
    for index in range(3):
        queue.enqueue("event", {"n": index})

    queue.trim()
    counts = queue.counts()
    assert counts.get("event", 0) == 3
    assert counts.get("measurement", 0) == 2
    queue.close()
