"""Testes da importacao do .hubconn e da navegacao para o painel."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from desktop import app as desktop
from shared.connection_file import build_connection, write_connection

CERT = "-----BEGIN CERTIFICATE-----\nMIIBfake\n-----END CERTIFICATE-----\n"


def make_connection(base_url: str = "https://192.168.0.110:8443") -> dict:
    return build_connection(
        store_name="Mercado Bertolo",
        base_url=base_url,
        agent_token="agente-" + "x" * 40,
        ca_certificate_pem=CERT,
        server_name="SERVIDOR",
    )


def test_painel_do_servidor_e_a_propria_api():
    assert desktop.panel_url({"mode": "server", "api_url": "https://127.0.0.1:8443/"}) == (
        "https://127.0.0.1:8443/"
    )


def test_servidor_sem_endereco_nao_abre_painel():
    assert desktop.panel_url({"mode": "server", "api_url": ""}) is None


def test_agente_usa_o_endereco_da_loja_do_arquivo_de_conexao(tmp_path, monkeypatch):
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    target = tmp_path / "HUBMonitor" / "connection.json"
    write_connection(target, make_connection("https://10.0.0.9:9443"))

    assert desktop.panel_url({"mode": "agent"}) == "https://10.0.0.9:9443/"


def test_agente_sem_conexao_nao_abre_painel(tmp_path, monkeypatch):
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    assert desktop.panel_url({"mode": "agent"}) is None


def test_importacao_grava_o_arquivo_na_pasta_restrita(tmp_path, monkeypatch):
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    monkeypatch.setattr(desktop, "_wait_agent_health", lambda timeout=25.0: True)
    origem = tmp_path / "loja.hubconn"
    write_connection(origem, make_connection())

    codigo = desktop.import_connection_cli(str(origem))
    assert codigo == 0

    destino = tmp_path / "HUBMonitor" / "connection.json"
    assert destino.is_file()
    data = json.loads(destino.read_text(encoding="utf-8"))
    assert data["base_url"] == "https://192.168.0.110:8443"
    assert data.get("fiscal") is None or isinstance(data.get("fiscal"), dict)


def test_importacao_recusa_arquivo_invalido(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    ruim = tmp_path / "ruim.hubconn"
    ruim.write_text("nao e json", encoding="utf-8")

    assert desktop.import_connection_cli(str(ruim)) == 2
    assert not (tmp_path / "HUBMonitor" / "connection.json").exists()
    assert "invalido" in capsys.readouterr().err.lower()


def test_importacao_nao_sobrescreve_com_arquivo_adulterado(tmp_path, monkeypatch):
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    destino = tmp_path / "HUBMonitor" / "connection.json"
    write_connection(destino, make_connection("https://192.168.0.110:8443"))

    adulterado = tmp_path / "adulterado.hubconn"
    data = make_connection("https://10.9.9.9:8443")
    data["agent_token"] = "invasor-" + "y" * 40
    adulterado.write_text(json.dumps(data), encoding="utf-8")

    assert desktop.import_connection_cli(str(adulterado)) == 2
    assert json.loads(destino.read_text(encoding="utf-8"))["base_url"] == "https://192.168.0.110:8443"

FAKE_HEALTH = {
    "status": "ok",
    "machine_name": "CAIXA02",
    "monitors": {
        "gateway": {"ok": True, "latency_ms": 1.0},
        "internet": {"ok": True, "latency_ms": 12.0},
        "sefaz_tcp": {"ok": True, "latency_ms": 40.0},
        "server": {"ok": False, "latency_ms": None},
    },
    "queue": {"total": 0},
    "time_utc": "2026-10-17T00:00:00Z",
}


def _status_item(data, label):
    return next(item for item in data["items"] if item["label"] == label)


def test_sem_conexao_importada_marca_pendencia(tmp_path, monkeypatch):
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    monkeypatch.setattr(desktop, "_http_get", lambda *args, **kwargs: FAKE_HEALTH)

    data = desktop.collect_status({"mode": "agent", "api_url": "http://127.0.0.1:8010"})

    assert data["needs_connection"] is True
    item = _status_item(data, "Comunicação com o servidor")
    assert item["state"] == "unknown"
    assert "Importar" in item["detail"]


def test_com_conexao_importada_usa_o_monitor(tmp_path, monkeypatch):
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    write_connection(tmp_path / "HUBMonitor" / "connection.json", make_connection())
    monkeypatch.setattr(desktop, "_http_get", lambda *args, **kwargs: FAKE_HEALTH)

    data = desktop.collect_status({"mode": "agent", "api_url": "http://127.0.0.1:8010"})

    assert data["needs_connection"] is False
    item = _status_item(data, "Comunicação com o servidor")
    assert item["state"] == "fail"


def test_ps_quote_escapa_apostrofo():
    assert desktop.ps_quote("Joao's") == "'Joao''s'"
    assert desktop.ps_quote("simples") == "'simples'"


def test_comando_de_elevacao_sobrevive_a_apostrofo_no_caminho(tmp_path):
    origem = tmp_path / "Joao's.hubconn"
    comando = desktop.elevation_command(r"C:\Program Files\HUB\HUBMonitor.exe", origem)

    assert "RunAs" in comando
    assert "'ui','--import-connection'," in comando
    assert origem.as_posix().replace("'", "''") in comando.replace("\\", "/")

def test_servidor_lista_os_computadores(monkeypatch):
    payload = {
        "store_name": "Mercado Bertolo",
        "machines": [
            {
                "machine_name": "CAIXA02",
                "online": True,
                "last_seen": "2026-10-17T00:00:00Z",
                "diagnosis": "Tudo normal",
            },
            {
                "machine_name": "CAIXA03",
                "online": False,
                "last_seen": None,
                "diagnosis": "Sem comunicação há 12 min",
            },
        ],
        "incidents": [],
    }
    monkeypatch.setattr(desktop, "_http_get", lambda *args, **kwargs: payload)

    data = desktop.collect_status({"mode": "server", "api_url": "https://127.0.0.1:8443"})

    assert [item["name"] for item in data["machines"]] == ["CAIXA02", "CAIXA03"]
    assert data["machines"][0]["state"] == "ok"
    assert data["machines"][1]["state"] == "fail"
    assert data["machines"][1]["last_seen"] == ""

def test_importacao_confirma_o_agente(tmp_path, monkeypatch):
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    origem = tmp_path / "loja.hubconn"
    write_connection(origem, make_connection())
    monkeypatch.setattr(desktop, "_wait_agent_health", lambda timeout=25.0: True)

    assert desktop.import_connection_cli(str(origem)) == 0
    assert (tmp_path / "HUBMonitor" / "connection.json").is_file()


def test_importacao_avisa_quando_o_agente_nao_volta(tmp_path, monkeypatch):
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    origem = tmp_path / "loja.hubconn"
    write_connection(origem, make_connection())
    monkeypatch.setattr(desktop, "_wait_agent_health", lambda timeout=25.0: False)

    # 4 = gravado, mas sem confirmacao do agente.
    assert desktop.import_connection_cli(str(origem)) == 4
    assert (tmp_path / "HUBMonitor" / "connection.json").is_file()


def test_janela_avisa_quando_o_agente_nao_confirma(monkeypatch):
    class Resultado:
        stdout = "4\n"
        stderr = ""

    monkeypatch.setattr(desktop.subprocess, "run", lambda *a, **k: Resultado())
    resposta = desktop._install_connection_elevated(Path("loja.hubconn"))

    assert resposta["ok"] is True
    assert "nao respondeu" in resposta["detail"]

def test_janela_mostra_a_ultima_verificacao(monkeypatch):
    payload = {
        "status": "ok",
        "machine_name": "CAIXA02",
        "monitors": {
            "internet": {"ok": True, "latency_ms": 12.0, "checked_at": "2026-10-17T10:00:00Z"},
            "sefaz_tcp": {"ok": True, "latency_ms": 40.0, "checked_at": "2026-10-17T10:00:20Z"},
            "server": {"ok": True, "latency_ms": 5.0, "checked_at": "2026-10-17T09:59:00Z"},
        },
        "queue": {"total": 0},
    }
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path := __import__("tempfile").mkdtemp()))
    monkeypatch.setattr(desktop, "_http_get", lambda *args, **kwargs: payload)

    data = desktop.collect_status({"mode": "agent", "api_url": "http://127.0.0.1:8010"})

    assert data["last_check"] == "2026-10-17T10:00:20Z"


def test_janela_sem_verificacao_nao_inventa_horario(monkeypatch):
    monkeypatch.setenv("PROGRAMDATA", __import__("tempfile").mkdtemp())
    monkeypatch.setattr(
        desktop,
        "_http_get",
        lambda *args, **kwargs: {"status": "ok", "machine_name": "CAIXA02", "monitors": {}, "queue": {}},
    )

    data = desktop.collect_status({"mode": "agent", "api_url": "http://127.0.0.1:8010"})

    assert data["last_check"] is None

def test_resumo_da_bandeja_mostra_os_tres_estados():
    status = {
        "items": [
            {"label": "Internet", "state": "ok"},
            {"label": "Acesso à SEFAZ", "state": "fail"},
            {"label": "Comunicação com o servidor", "state": "unknown"},
        ]
    }
    texto = desktop.tray_summary(status)

    assert "Internet: normal" in texto
    assert "Acesso à SEFAZ: falha" in texto
    assert "Comunicação com o servidor: sem dados" in texto


def test_resumo_da_bandeja_sem_dados_nao_inventa():
    assert "sem dados" in desktop.tray_summary({})


def test_menu_da_bandeja_tem_as_quatro_acoes():
    fonte = Path(desktop.__file__).read_text(encoding="utf-8")
    bloco = fonte.split("menu = pystray.Menu(", 1)[1]
    assert "Abrir a janela" in bloco
    assert "Importar conexão" in bloco
    assert "Sair da bandeja" in bloco
    assert "tray_summary" in fonte
