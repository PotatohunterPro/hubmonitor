"""Internet: confirmacao por TCP quando o ICMP nao responde."""

from __future__ import annotations

import asyncio

import agent.monitors.internet as mod
from agent.config import AgentSettings


class Ping:
    def __init__(self, host, ok, latency=None, error=None):
        self.host = host
        self.ok = ok
        self.latency_ms = latency
        self.loss_pct = 0.0 if ok else 100.0
        self.error = error


def make_settings(monkeypatch, tmp_path) -> AgentSettings:
    monkeypatch.setenv("CONNECTION_FILE", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    return AgentSettings.from_env()


def test_icmp_bloqueado_mas_tcp_responde_nao_e_falha(monkeypatch, tmp_path):
    async def ping_falha(host, timeout):
        return Ping(host, False, error="timeout")

    tentativas = []

    async def tcp_ok(host, port, timeout):
        tentativas.append((host, port))
        return (True, 9.0, "1.1.1.1", None)

    monkeypatch.setattr(mod, "ping_once", ping_falha)
    monkeypatch.setattr(mod, "tcp_connect", tcp_ok)

    monitor = mod.InternetMonitor(make_settings(monkeypatch, tmp_path))
    result = asyncio.run(monitor.check())

    assert result.ok is True
    assert result.details["icmp_blocked"] is True
    assert result.details["tcp_fallback"]["port"] == 443
    assert result.latency_ms == 9.0
    assert tentativas


def test_icmp_ok_nao_dispara_tcp(monkeypatch, tmp_path):
    chamadas = []

    async def ping_ok(host, timeout):
        return Ping(host, True, latency=12.0)

    async def tcp_nunca(host, port, timeout):
        chamadas.append(host)
        return (True, 1.0, host, None)

    monkeypatch.setattr(mod, "ping_once", ping_ok)
    monkeypatch.setattr(mod, "tcp_connect", tcp_nunca)

    monitor = mod.InternetMonitor(make_settings(monkeypatch, tmp_path))
    result = asyncio.run(monitor.check())

    assert result.ok is True
    assert result.details["icmp_blocked"] is False
    assert result.details["tcp_fallback"] is None
    assert chamadas == []


def test_icmp_e_tcp_falhando_e_falha_de_verdade(monkeypatch, tmp_path):
    async def ping_falha(host, timeout):
        return Ping(host, False, error="sem rota")

    async def tcp_falha(host, port, timeout):
        return (False, None, None, "recusado")

    monkeypatch.setattr(mod, "ping_once", ping_falha)
    monkeypatch.setattr(mod, "tcp_connect", tcp_falha)

    monitor = mod.InternetMonitor(make_settings(monkeypatch, tmp_path))
    result = asyncio.run(monitor.check())

    assert result.ok is False
    assert result.details["icmp_blocked"] is False
    assert "sem rota" in result.error
