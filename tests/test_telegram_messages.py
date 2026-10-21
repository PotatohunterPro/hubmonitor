from __future__ import annotations

from unittest.mock import Mock

from server.config import ServerSettings
from server.services.telegram import TelegramNotifier
from shared import constants as C
from shared.timeutil import to_iso, utc_now
from tests.conftest import status


def test_incident_notification_is_plain_language_and_marks_diagnosis_as_hypothesis(settings):
    settings.store_name = "LOJA TESTE"
    notifier = TelegramNotifier(settings, Mock())
    started_at = to_iso(utc_now())
    incident = {
        "type": C.COMPONENT_SEFAZ_TCP,
        "affected_machines": ["CAIXA01"],
        "diagnosis": "Problema localizado no CAIXA01. Rede e internet estavam normais.",
        "started_at": started_at,
    }

    message = notifier.format_incident(
        incident,
        {"CAIXA01": status("CAIXA01", sefaz_tcp_ok=False)},
    )

    assert "HUB Monitor | Sinal de atenção" in message
    assert "Loja: LOJA TESTE" in message
    assert "Acesso à SEFAZ" in message
    assert "Leitura automática (hipótese, requer confirmação)" in message
    assert "não confirma a causa final" in message
    assert "horário comercial" in message
    assert "SEFAZ TCP" not in message


def test_daily_summary_distinguishes_no_data_from_no_incidents(settings):
    notifier = TelegramNotifier(settings, Mock())

    message = notifier.format_daily_summary({}, [], [], [])

    assert "Resumo das últimas 24 horas" in message
    assert "Sem dados suficientes para calcular a disponibilidade" in message
    assert "Nenhum caixa enviou dados no período" in message
    assert "Nenhuma ocorrência registrada no período" not in message


def test_daily_summary_is_enabled_by_default_for_service(monkeypatch):
    from server import config

    monkeypatch.setattr(config, "load_env", lambda: None)
    monkeypatch.delenv("TELEGRAM_DAILY_SUMMARY", raising=False)
    settings = ServerSettings.from_env()

    assert settings.telegram_daily_summary is True

def _ocorrencia(**extra) -> dict:
    from datetime import timedelta

    agora = utc_now().replace(microsecond=0)
    dados = {
        "id": 1,
        "type": C.COMPONENT_INTERNET,
        "started_at": to_iso(agora - timedelta(minutes=10)),
        "recovered_at": to_iso(agora),
        "duration_seconds": 600.0,
        "observed_duration_seconds": 300.0,
        "unobserved_seconds": 300.0,
        "affected_machines": ["CAIXA02"],
    }
    dados.update(extra)
    return dados


def test_recuperacao_mostra_o_tempo_sem_observacao(settings):
    texto = TelegramNotifier(settings, Mock()).format_recovery(_ocorrencia())

    assert "Duração observada" in texto
    assert "Períodos sem observação" in texto


def test_recuperacao_sem_lacuna_nao_inventa_linha(settings):
    texto = TelegramNotifier(settings, Mock()).format_recovery(_ocorrencia(unobserved_seconds=0.0))

    assert "Períodos sem observação" not in texto
