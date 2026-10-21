"""Testes da exportacao do arquivo de conexao pelo servidor."""

from __future__ import annotations

import os

import pytest

from server.config import ServerSettings
from server.services import connection_export as ce
from server.tls import generate_local_certificate
from shared.connection_file import read_connection


@pytest.fixture()
def servidor(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "b.db"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("AGENT_INGEST_TOKEN", "token-de-loja-1234567890")
    monkeypatch.setenv("STORE_NAME", "Mercado Bertolo")
    monkeypatch.setenv("SERVER_PORT", "8443")
    settings = ServerSettings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    cert, key, _ca = generate_local_certificate(
        settings.data_dir / "certs", "SERVIDOR", "192.168.0.110"
    )
    settings.tls_cert_file = cert
    settings.tls_key_file = key
    return settings


def test_url_publica_usa_a_porta_configurada(servidor, monkeypatch):
    monkeypatch.setattr("agent.config.detect_local_ip", lambda *_: "10.1.2.3")
    assert ce._detect_public_url(servidor) == "https://10.1.2.3:8443"


def test_url_publica_nao_desloca_porta_8000(servidor, monkeypatch):
    monkeypatch.setattr("agent.config.detect_local_ip", lambda *_: "10.1.2.3")
    servidor.port = 8000
    assert ce._detect_public_url(servidor).endswith(":8000")


def test_exportacao_inclui_destino_fiscal(servidor, tmp_path, monkeypatch):
    monkeypatch.setattr("agent.config.detect_local_ip", lambda *_: "10.1.2.3")
    monkeypatch.setenv("FISCAL_UF", "SP")
    monkeypatch.setenv("FISCAL_DOCUMENT", "nfce")
    monkeypatch.setenv("SEFAZ_HOST", "nfce.fazenda.sp.gov.br")
    monkeypatch.setenv("SEFAZ_PORT", "443")

    destino = ce.export_connection(servidor, tmp_path / "loja.hubconn")
    data = read_connection(destino)
    assert data["base_url"] == "https://10.1.2.3:8443"
    assert data["fiscal"]["uf"] == "SP"
    assert data["fiscal"]["host"] == "nfce.fazenda.sp.gov.br"
    assert "PRIVATE KEY" not in destino.read_text(encoding="utf-8")


def test_exportacao_sem_credencial_falha(servidor, tmp_path, monkeypatch):
    servidor.agent_ingest_token = ""
    with pytest.raises(ValueError):
        ce.export_connection(servidor, tmp_path / "loja.hubconn")


def test_exportacao_sem_certificado_falha(servidor, tmp_path, monkeypatch):
    servidor.tls_cert_file = None
    servidor.data_dir = tmp_path / "vazia"
    with pytest.raises(FileNotFoundError):
        ce.export_connection(servidor, tmp_path / "loja.hubconn")

def test_exportacao_le_o_destino_do_env_gravado(servidor, monkeypatch, tmp_path):
    """Salvar a configuracao grava no .env sem mexer em os.environ."""
    for chave in (
        "FISCAL_UF", "FISCAL_DOCUMENT", "SEFAZ_HOST", "SEFAZ_PORT", "FISCAL_ENDPOINT_CONFIRMED"
    ):
        monkeypatch.delenv(chave, raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "FISCAL_UF=SP\nFISCAL_DOCUMENT=nfce\nSEFAZ_HOST=nfce.fazenda.sp.gov.br\n"
        "SEFAZ_PORT=443\nFISCAL_ENDPOINT_CONFIRMED=true\n",
        encoding="utf-8",
    )
    servidor.env_file = env_file

    data = ce.build_store_connection(servidor, public_url="https://192.168.0.110:8443")

    assert data["fiscal"] is not None
    assert data["fiscal"]["uf"] == "SP"
    assert data["fiscal"]["host"] == "nfce.fazenda.sp.gov.br"
    assert "FISCAL_UF" not in os.environ


def test_exportacao_sem_env_cai_no_ambiente(servidor, monkeypatch):
    servidor.env_file = None
    monkeypatch.setenv("FISCAL_UF", "MG")
    monkeypatch.setenv("SEFAZ_HOST", "nfce.fazenda.mg.gov.br")
    monkeypatch.setenv("SEFAZ_PORT", "443")
    monkeypatch.setenv("FISCAL_ENDPOINT_CONFIRMED", "true")

    data = ce.build_store_connection(servidor, public_url="https://192.168.0.110:8443")

    assert data["fiscal"] is not None
    assert data["fiscal"]["uf"] == "MG"
