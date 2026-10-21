"""Testes do envio efetivo das notificacoes (outbox -> Telegram).

Cobrem o caminho que decide entre abertura, recuperacao e resumo
retrospectivo. Antes, so a decisao pura (plan_notification) era testada;
o laco que realmente envia nunca tinha sido executado.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from server.context import ServerContext
from server.database.db import Database
from server.main import drain_notifications
from server.services.incidents import IncidentManager
from server.services.occurrences import Observation, OccurrenceEngine
from shared import constants as C
from shared.timeutil import utc_now

BASE = utc_now().replace(microsecond=0) - timedelta(hours=2)


class FakeNotifier:
    enabled = True

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.fail = False

    async def send(self, text: str) -> bool:
        if self.fail:
            return False
        self.sent.append(text)
        return True

    def format_incident(self, incident, statuses) -> str:
        return "ABERTURA"

    def format_recovery(self, incident) -> str:
        return "RECUPERACAO"

    def format_retrospective(self, incident) -> str:
        return "RETROSPECTIVA"


def make_context(db: Database, settings) -> ServerContext:
    return ServerContext(
        settings=settings,
        db=db,
        http=None,  # type: ignore[arg-type]
        mikrotik=None,  # type: ignore[arg-type]
        notifier=FakeNotifier(),  # type: ignore[arg-type]
        incidents=IncidentManager(db, settings),
    )


def observe(engine: OccurrenceEngine, component: str, samples) -> None:
    engine.observe(
        [Observation("CAIXA02", component, BASE + timedelta(seconds=s), ok, "replay") for s, ok in samples]
    )


def test_ocorrencia_encerrada_envia_um_unico_resumo_retrospectivo(db: Database, settings):
    engine = OccurrenceEngine(db, settings)
    observe(
        engine,
        C.COMPONENT_INTERNET,
        [(0, False), (10, False), (20, False), (40, True), (60, True), (80, True)],
    )
    ctx = make_context(db, settings)

    import asyncio

    asyncio.run(drain_notifications(ctx))

    assert ctx.notifier.sent == ["RETROSPECTIVA"]

    asyncio.run(drain_notifications(ctx))
    assert len(ctx.notifier.sent) == 1, "nao pode reenviar a mesma ocorrencia"


def test_ocorrencia_aberta_envia_abertura(db: Database, settings):
    engine = OccurrenceEngine(db, settings)
    observe(engine, C.COMPONENT_SEFAZ_TCP, [(0, False), (10, False), (20, False)])
    ctx = make_context(db, settings)

    import asyncio

    asyncio.run(drain_notifications(ctx))
    assert ctx.notifier.sent == ["ABERTURA"]

    asyncio.run(drain_notifications(ctx))
    assert len(ctx.notifier.sent) == 1


def test_recuperacao_apos_abertura_envia_dois_avisos(db: Database, settings):
    engine = OccurrenceEngine(db, settings)
    ctx = make_context(db, settings)

    import asyncio

    observe(engine, C.COMPONENT_INTERNET, [(0, False), (10, False), (20, False)])
    asyncio.run(drain_notifications(ctx))
    assert ctx.notifier.sent == ["ABERTURA"]

    observe(engine, C.COMPONENT_INTERNET, [(40, True), (60, True), (80, True)])
    asyncio.run(drain_notifications(ctx))
    assert ctx.notifier.sent == ["ABERTURA", "RECUPERACAO"]


def test_sintoma_consolidado_nao_envia_mensagem_propria(db: Database, settings):
    engine = OccurrenceEngine(db, settings)
    observations = []
    for index in range(3):
        for component in (C.COMPONENT_INTERNET, C.COMPONENT_DNS):
            observations.append(
                Observation("CAIXA02", component, BASE + timedelta(seconds=index * 10), False, "replay")
            )
    engine.observe(observations)
    engine.consolidate()

    ctx = make_context(db, settings)
    import asyncio

    asyncio.run(drain_notifications(ctx))
    assert ctx.notifier.sent == ["ABERTURA"]


def test_falha_do_envio_mantem_a_notificacao_pendente(db: Database, settings):
    engine = OccurrenceEngine(db, settings)
    observe(engine, C.COMPONENT_SEFAZ_TLS, [(0, False), (10, False), (20, False)])

    ctx = make_context(db, settings)
    ctx.notifier.fail = True  # type: ignore[attr-defined]

    import asyncio

    asyncio.run(drain_notifications(ctx))
    assert ctx.notifier.sent == []
    assert db.notification_summary()["pending"] == 1

    ctx.notifier.fail = False  # type: ignore[attr-defined]
    asyncio.run(drain_notifications(ctx))
    assert ctx.notifier.sent == ["ABERTURA"]
    assert db.notification_summary()["pending"] == 0
