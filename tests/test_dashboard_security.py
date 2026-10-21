from __future__ import annotations

from pathlib import Path
import asyncio
import logging
import stat
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from fastapi.testclient import TestClient
from dotenv import dotenv_values

from server.main import create_app
from server.services.config_store import save_env_values
from server.services.telegram import TelegramNotifier


def test_dashboard_escapes_dynamic_values_before_inner_html():
    template = Path(__file__).resolve().parents[1] / "server/dashboard/templates/dashboard.html"
    source = template.read_text(encoding="utf-8")
    assert "function esc(value)" in source
    assert ".replace(/</g, '&lt;')" in source
    assert "esc(m.machine_name)" in source
    assert "esc(diagnosisLabel(m.diagnosis))" in source
    assert "esc(e.message || e.component || '')" in source
    assert "esc(item.diagnosis || 'Dados insuficientes')" in source
    assert "esc(w.probe || '-')" in source
    assert "active || 'Não identificado'" in source


def test_primeira_senha_so_pode_ser_criada_no_servidor(settings, tmp_path):
    settings.env_file = tmp_path / ".env"
    settings.env_file.write_text("AGENT_INGEST_TOKEN=test-agent-token\n", encoding="utf-8")
    app = create_app(settings)
    with TestClient(app, client=("192.0.2.45", 50000)) as client:
        assert client.get("/api/v1/admin/status").json()["can_setup"] is False
        response = client.post(
            "/api/v1/admin/setup", json={"password": "uma-senha-local-forte"}
        )
        assert response.status_code == 403


def test_senha_local_protege_configuracao_e_token_fica_oculto(settings, tmp_path):
    settings.env_file = tmp_path / ".env"
    settings.env_file.write_text(
        "AGENT_INGEST_TOKEN=test-agent-token\nSERVER_PORT=8000\n", encoding="utf-8"
    )
    app = create_app(settings)
    token = "123456:token-secreto-do-bot"
    with TestClient(app, client=("127.0.0.1", 50001)) as client:
        assert client.get("/api/v1/admin/settings").status_code == 401
        assert client.get("/api/v1/admin/agent-token").status_code == 401
        setup = client.post(
            "/api/v1/admin/setup", json={"password": "uma-senha-local-forte"}
        )
        assert setup.status_code == 200
        assert "httponly" in setup.headers["set-cookie"].lower()

        payload = {
            "store_name": "Loja Piloto",
            "local_subnet": "192.168.30.0/24",
            "telegram_enabled": True,
            "telegram_bot_token": token,
            "telegram_chat_id": "-1001234567890",
            "mikrotik_enabled": False,
            "mikrotik_host": "192.168.30.1",
            "mikrotik_port": 8728,
            "mikrotik_user": "monitor-leitura",
            "mikrotik_password": "",
            "mikrotik_use_ssl": False,
        }
        saved = client.put("/api/v1/admin/settings", json=payload)
        assert saved.status_code == 200
        assert token not in saved.text

        config = client.get("/api/v1/admin/settings")
        assert config.status_code == 200
        assert config.json()["telegram_bot_configured"] is True
        assert "telegram_bot_token" not in config.json()
        assert "agent_ingest_token" not in config.json()
        assert token not in config.text
        assert app.state.ctx.settings.store_name == "Loja Piloto"
        assert app.state.ctx.settings.local_subnet == "192.168.30.0/24"
        assert app.state.ctx.notifier.enabled is True

        agent_token = client.get("/api/v1/admin/agent-token")
        assert agent_token.status_code == 200
        assert agent_token.json()["agent_ingest_token"] == "test-agent-token"
        assert agent_token.headers["cache-control"] == "no-store"

        values = dotenv_values(settings.env_file, interpolate=False)
        assert values["TELEGRAM_BOT_TOKEN"] == token
        assert values["TELEGRAM_CHAT_ID"] == "-1001234567890"
        assert values["STORE_NAME"] == "Loja Piloto"
        assert stat.S_IMODE(settings.env_file.stat().st_mode) == 0o600

        assert client.post("/api/v1/admin/logout").status_code == 200
        assert client.get("/api/v1/admin/settings").status_code == 401
        assert client.post(
            "/api/v1/admin/login", json={"password": "uma-senha-local-forte"}
        ).status_code == 200
        assert client.get("/api/v1/admin/settings").status_code == 200


def test_teste_telegram_valida_bot_e_grupo_sem_retornar_token(settings, tmp_path, monkeypatch):
    settings.env_file = tmp_path / ".env"
    settings.env_file.write_text("AGENT_INGEST_TOKEN=test-agent-token\n", encoding="utf-8")
    app = create_app(settings)
    token = "123456:token-secreto-do-bot"
    with TestClient(app, client=("127.0.0.1", 50002)) as client:
        client.post("/api/v1/admin/setup", json={"password": "uma-senha-local-forte"})
        context = app.state.ctx
        context.http.get = AsyncMock(
            return_value=SimpleNamespace(
                status_code=200,
                json=lambda: {"ok": True, "result": {"id": 123456, "username": "hub_bot"}},
            )
        )
        context.http.post = AsyncMock(
            return_value=SimpleNamespace(status_code=200, json=lambda: {"ok": True})
        )

        response = client.post(
            "/api/v1/admin/telegram/test",
            json={"telegram_bot_token": token, "telegram_chat_id": "-1001234567890"},
        )
        assert response.status_code == 200
        assert response.json()["bot_id"] == 123456
        assert response.json()["bot_username"] == "hub_bot"
        assert token not in response.text
        context.http.get.assert_awaited_once()
        context.http.post.assert_awaited_once()


def test_credencial_do_agente_e_obrigatoria_no_teste_de_conexao(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/agent/check").status_code == 401
        response = client.get(
            "/api/v1/agent/check", headers={"Authorization": "Bearer test-agent-token"}
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True


def test_configuracao_painel_e_tela_de_ajustes_estao_disponiveis(settings):
    with TestClient(create_app(settings)) as client:
        dashboard = client.get("/")
        configuration = client.get("/configuracao")
        assert dashboard.status_code == 200
        assert 'href="/configuracao"' in dashboard.text
        assert configuration.status_code == 200
        assert "Token do bot" in configuration.text
        assert "ID do grupo" in configuration.text
        assert "bot_id" in configuration.text


def test_teste_telegram_exibe_erro_util_sem_revelar_token(settings, tmp_path):
    settings.env_file = tmp_path / ".env"
    settings.env_file.write_text("AGENT_INGEST_TOKEN=test-agent-token\n", encoding="utf-8")
    app = create_app(settings)
    token = "123456:token-secreto-do-bot"
    with TestClient(app, client=("127.0.0.1", 50003)) as client:
        client.post("/api/v1/admin/setup", json={"password": "uma-senha-local-forte"})
        context = app.state.ctx
        context.http.get = AsyncMock(
            return_value=SimpleNamespace(status_code=401, json=lambda: {"ok": False})
        )
        invalid_token = client.post(
            "/api/v1/admin/telegram/test",
            json={"telegram_bot_token": token, "telegram_chat_id": "-1001234567890"},
        )
        assert invalid_token.status_code == 422
        assert "BotFather" in invalid_token.json()["detail"]
        assert token not in invalid_token.text

        oversized = "x" * 300
        invalid_length = client.post(
            "/api/v1/admin/telegram/test",
            json={"telegram_bot_token": oversized, "telegram_chat_id": "-1001234567890"},
        )
        assert invalid_length.status_code == 422
        assert oversized not in invalid_length.text

        malformed_secret = "token-malformado-nao-ecoar"
        malformed = client.post(
            "/api/v1/admin/telegram/test",
            content=(
                '{"telegram_bot_token":"' + malformed_secret + '",'
                '"telegram_chat_id":'
            ),
            headers={"Content-Type": "application/json"},
        )
        assert malformed.status_code == 422
        assert malformed_secret not in malformed.text

        context.http.get = AsyncMock(
            return_value=SimpleNamespace(
                status_code=200,
                json=lambda: {"ok": True, "result": {"id": 123456, "username": "hub_bot"}},
            )
        )
        context.http.post = AsyncMock(
            return_value=SimpleNamespace(
                status_code=400,
                json=lambda: {"ok": False, "description": "chat not found"},
            )
        )
        invalid_group = client.post(
            "/api/v1/admin/telegram/test",
            json={"telegram_bot_token": token, "telegram_chat_id": "-1001234567890"},
        )
        assert invalid_group.status_code == 422
        assert "adicione o bot ao grupo" in invalid_group.json()["detail"]
        assert token not in invalid_group.text


def test_assistente_visual_do_caixa_nao_pede_dados_do_telegram():
    root = Path(__file__).resolve().parents[1]
    source = (root / "install/windows/lib/AgentWizard.ps1").read_text(encoding="utf-8")
    assert "System.Windows.Forms" in source
    assert "Testar conexão" in source
    assert "/api/v1/agent/check" in source
    assert "TELEGRAM_BOT_TOKEN" not in source
    assert "TELEGRAM_CHAT_ID" not in source


def test_arquivo_de_configuracao_preserva_valores_e_escapa_segredos(tmp_path):
    path = tmp_path / ".env"
    path.write_text("AGENT_INGEST_TOKEN=agent-token\nCUSTOM_VALUE=keep-me\n", encoding="utf-8")
    secret = 'senha com espaco, #, "aspas" e \\ barra'
    save_env_values(path, {"MIKROTIK_PASSWORD": secret})
    values = dotenv_values(path, interpolate=False)
    assert values["AGENT_INGEST_TOKEN"] == "agent-token"
    assert values["CUSTOM_VALUE"] == "keep-me"
    assert values["MIKROTIK_PASSWORD"] == secret


def test_duas_instalacoes_locais_mantem_configuracoes_separadas(settings, tmp_path):
    clients = []
    apps = []
    for name in ("Cliente Alfa", "Cliente Beta"):
        directory = tmp_path / name.replace(" ", "-")
        directory.mkdir()
        env_file = directory / ".env"
        env_file.write_text("AGENT_INGEST_TOKEN=test-agent-token\n", encoding="utf-8")
        store_settings = replace(
            settings,
            data_dir=directory / "data",
            log_dir=directory / "logs",
            db_path=directory / "data" / "monitor.db",
            env_file=env_file,
        )
        app = create_app(store_settings)
        apps.append(app)
        clients.append(TestClient(app, client=("127.0.0.1", 50100 + len(clients))))

    with clients[0] as alpha, clients[1] as beta:
        for client, name, password in (
            (alpha, "Cliente Alfa", "senha-administrativa-alfa"),
            (beta, "Cliente Beta", "senha-administrativa-beta"),
        ):
            assert client.post("/api/v1/admin/setup", json={"password": password}).status_code == 200
            saved = client.put(
                "/api/v1/admin/settings",
                json={
                    "store_name": name,
                    "local_subnet": "192.168.0.0/24",
                    "telegram_enabled": False,
                    "mikrotik_enabled": False,
                },
            )
            assert saved.status_code == 200
        assert alpha.get("/api/v1/admin/settings").json()["store_name"] == "Cliente Alfa"
        assert beta.get("/api/v1/admin/settings").json()["store_name"] == "Cliente Beta"
        assert apps[0].state.admin_auth.path != apps[1].state.admin_auth.path


def test_notifier_nao_registra_token_quando_rede_falha(settings, caplog):
    token = "123456:token-que-nao-pode-ir-para-o-log"

    async def fail_request(request):
        raise httpx.ConnectError(f"falha em https://api.telegram.org/bot{token}/sendMessage", request=request)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fail_request)) as http:
            notifier = TelegramNotifier(settings, http)
            notifier.settings.telegram_bot_token = token
            notifier.settings.telegram_chat_id = "-1001234567890"
            notifier.settings.telegram_enabled = True
            assert await notifier.send("teste") is False

    with caplog.at_level(logging.WARNING, logger="server.telegram"):
        asyncio.run(run())
    assert token not in caplog.text
