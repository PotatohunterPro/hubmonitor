"""Testes da configuracao fiscal por UF."""

from __future__ import annotations

import json

import pytest

from agent.config import AgentSettings
from shared import fiscal
from shared.connection_file import ConnectionFileError, build_connection, read_connection, write_connection

CERT = "-----BEGIN CERTIFICATE-----\nMIIBfake\n-----END CERTIFICATE-----\n"
TOKEN = "agente-" + "x" * 40


def make_connection(fiscal_block=None):
    return build_connection(
        store_name="Mercado Bertolo",
        base_url="https://192.168.0.110:8443",
        agent_token=TOKEN,
        ca_certificate_pem=CERT,
        server_name="SERVIDOR",
        fiscal=fiscal_block,
    )


def test_aceita_uf_e_documento_validos():
    target = fiscal.validate_target(uf="sp", document="nfce", host="nfce.fazenda.sp.gov.br")
    assert target.uf == "SP"
    assert target.document == "nfce"
    assert target.address == "nfce.fazenda.sp.gov.br:443"


def test_recusa_uf_invalida():
    with pytest.raises(fiscal.FiscalConfigError):
        fiscal.validate_target(uf="XX", document="nfce", host="exemplo.com.br")


def test_recusa_documento_invalido():
    with pytest.raises(fiscal.FiscalConfigError):
        fiscal.validate_target(uf="SP", document="cte", host="exemplo.com.br")


def test_recusa_endereco_com_esquema_ou_local():
    for host in ("https://nfce.fazenda.sp.gov.br", "localhost", "127.0.0.1", "10.0.0.1"):
        with pytest.raises(fiscal.FiscalConfigError):
            fiscal.validate_target(uf="SP", document="nfce", host=host)


def test_recusa_porta_invalida():
    with pytest.raises(fiscal.FiscalConfigError):
        fiscal.validate_target(uf="SP", document="nfce", host="exemplo.com.br", port=70000)


def test_sugestao_existe_apenas_onde_e_documentada():
    assert fiscal.suggest_host("SP", "nfce") == "nfce.fazenda.sp.gov.br"
    assert fiscal.suggest_host("BA", "nfce") is None


def test_opcoes_cobrem_as_27_ufs():
    opcoes = fiscal.options()
    assert len(opcoes) == 27
    assert {item["uf"] for item in opcoes} == set(fiscal.UF_LIST)


def test_env_ida_e_volta():
    target = fiscal.validate_target(uf="SP", document="nfe", host="nfe.fazenda.sp.gov.br", confirmed=True)
    values = fiscal.env_values(target)
    assert values["SEFAZ_HOST"] == "nfe.fazenda.sp.gov.br"
    assert fiscal.from_env(values) == target


def test_env_ausente_nao_configura():
    assert fiscal.from_env({}) is None
    assert fiscal.from_env({"FISCAL_UF": "SP"}) is None


def test_probe_recusa_endereco_invalido_sem_rede():
    resultado = fiscal.probe("localhost")
    assert resultado["ok"] is False
    assert resultado["stage"] == "validacao"


def test_arquivo_de_conexao_carrega_o_destino_fiscal(tmp_path):
    path = tmp_path / "loja.hubconn"
    write_connection(
        path,
        make_connection(
            {"uf": "SP", "document": "nfce", "host": "nfce.fazenda.sp.gov.br", "confirmed": True}
        ),
    )
    data = read_connection(path)
    assert data["fiscal"]["uf"] == "SP"
    assert data["fiscal"]["host"] == "nfce.fazenda.sp.gov.br"


def test_arquivo_de_conexao_recusa_fiscal_invalido(tmp_path):
    data = make_connection()
    data["fiscal"] = {"uf": "XX", "document": "nfce", "host": "exemplo.com.br"}
    data.pop("fingerprint", None)
    from shared.connection_file import compute_fingerprint

    data["fingerprint"] = compute_fingerprint(data)
    path = tmp_path / "ruim.hubconn"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConnectionFileError, match="fiscal"):
        read_connection(path)


def test_agente_usa_o_destino_fiscal_da_loja(tmp_path, monkeypatch):
    path = tmp_path / "loja.hubconn"
    write_connection(
        path,
        make_connection(
            {"uf": "BA", "document": "nfe", "host": "nfe.sefaz.ba.gov.br", "port": 443}
        ),
    )
    monkeypatch.setenv("CONNECTION_FILE", str(path))
    monkeypatch.delenv("SEFAZ_HOST", raising=False)
    monkeypatch.delenv("SEFAZ_PORT", raising=False)

    settings = AgentSettings.from_env()
    assert settings.sefaz_host == "nfe.sefaz.ba.gov.br"
    assert settings.sefaz_port == 443
    assert settings.fiscal_uf == "BA"
