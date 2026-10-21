"""Servidor local do serviço HUB Monitoramento.

Uso:
    python -m server.main                 # sobe a API + dashboard + tarefas
    python -m server.main --print-config
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import logging
import secrets
import sys
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from agent.logging_setup import setup_logging
from server.api.routes import router
from server.config import ServerSettings
from server.context import ServerContext
from server.database.db import Database
from server.services.admin_auth import AdminAuthStore
from server.services.incidents import IncidentEvent, IncidentManager
from server.services.mikrotik import MikrotikService
from server.services.telegram import TelegramNotifier
from shared import constants as C
from shared.schemas import HealthResponse, WanStatus
from shared.timeutil import format_local, to_local, to_iso, utc_now

INCIDENT_INTERVAL_SECONDS = 5.0
NOTIFY_INTERVAL_SECONDS = 60.0
WAN_ALERT_CONFIRMATION_SAMPLES = 2
WAN_NOTIFY_INTERVAL_SECONDS = 5.0
OFFLINE_ALERT_AFTER_SECONDS = 300.0
OFFLINE_ALERT_REPEAT_SECONDS = 6 * 3600.0
UNKNOWN_WAN_RECORD_SECONDS = 60.0
DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"


# ======================================================================
# Tarefas de segundo plano
# ======================================================================
async def wan_loop(ctx: ServerContext) -> None:
    log = logging.getLogger("server.wan")
    last_unknown = 0.0
    while True:
        try:
            snapshot = await ctx.mikrotik.poll()
            ctx.last_wan_snapshot = snapshot
            if snapshot.ok:
                statuses = [
                    WanStatus(
                        timestamp=snapshot.checked_at,
                        wan_name=wan.wan_name,
                        provider=wan.provider,
                        status=wan.status,
                        probe=wan.probe,
                        latency_ms=wan.latency_ms,
                        active_route=wan.active_route,
                    )
                    for wan in snapshot.wans
                ]
                ctx.db.insert_wan_status(statuses)
                for wan in snapshot.wans:
                    transition = ctx.db.observe_wan_status(
                        wan_name=wan.wan_name,
                        provider=wan.provider,
                        status=wan.status,
                        timestamp=snapshot.checked_at,
                        probe=wan.probe,
                        active_route=wan.active_route,
                        confirmation_samples=WAN_ALERT_CONFIRMATION_SAMPLES,
                        max_sample_gap_seconds=max(
                            60.0, 3.0 * ctx.settings.mikrotik_poll_interval
                        ),
                    )
                    if transition:
                        log.info(
                            "Transicao da %s confirmada: %s",
                            wan.wan_name,
                            transition,
                        )
            else:
                now = time.time()
                if now - last_unknown >= UNKNOWN_WAN_RECORD_SECONDS:
                    last_unknown = now
                    ctx.db.insert_wan_status(
                        [
                            WanStatus(
                                timestamp=snapshot.checked_at,
                                wan_name=slot,
                                provider=ctx.settings.wan_provider(slot),
                                status="unknown",
                            )
                            for slot in C.WAN_SLOTS
                        ]
                    )
                    log.warning("MikroTik sem resposta: %s", snapshot.error)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Erro no ciclo de leitura das WANs")
        await asyncio.sleep(max(5, ctx.settings.mikrotik_poll_interval))


async def drain_notifications(ctx: ServerContext) -> None:
    """Envia a outbox persistente de notificacoes.

    O plano de cada notificacao decide entre:
      - open:          ocorrencia ainda aberta, alerta normal;
      - recovery:      ocorrencia que ja tinha sido anunciada;
      - retrospective: ocorrencia ja encerrada antes de conseguirmos avisar,
                       enviada uma unica vez como resumo;
      - skip:          sintoma consolidado em uma causa raiz.
    """
    if not ctx.notifier.enabled:
        return

    for plan, row in ctx.incidents.notification_plans():
        notification_id = int(row["notification_id"])
        incident_id = int(row["incident_id"])
        incident = ctx.db.incident_by_id(incident_id)
        if incident is None:
            ctx.db.mark_notification_sent(notification_id)
            continue

        if plan == "open":
            text = ctx.notifier.format_incident(incident, ctx.statuses())
        elif plan == "recovery":
            text = ctx.notifier.format_recovery(incident)
        else:
            text = ctx.notifier.format_retrospective(incident)

        if not await ctx.notifier.send(text):
            ctx.db.mark_notification_failed(notification_id, "falha ao enviar")
            continue

        ctx.db.mark_notification_sent(notification_id)

        if plan == "open":
            ctx.db.mark_incident_notified(incident_id, recovery=False)
            ctx.db.cancel_notification(f"{incident_id}:recovery", "ocorrencia reaberta")
        elif plan == "recovery":
            ctx.db.mark_incident_notified(incident_id, recovery=True)
        else:
            # O resumo retrospectivo cobre abertura e recuperacao.
            ctx.db.mark_incident_notified(incident_id, recovery=False)
            ctx.db.mark_incident_notified(incident_id, recovery=True)
            ctx.db.cancel_notification(f"{incident_id}:open", "enviada como resumo")
            ctx.db.cancel_notification(f"{incident_id}:recovery", "enviada como resumo")


async def drain_wan_notifications(ctx: ServerContext) -> None:
    """Entrega alertas WAN da outbox persistente, um por vez."""
    if not ctx.notifier.enabled:
        return

    while True:
        row = ctx.db.claim_next_wan_alert()
        if row is None:
            return

        kind = str(row.get("kind") or "")
        if kind == "down":
            message = ctx.notifier.format_wan_down(row)
        elif kind == "recovery":
            message = ctx.notifier.format_wan_recovery(row)
        elif kind == "retrospective":
            message = ctx.notifier.format_wan_retrospective(row)
        else:
            ctx.db.mark_wan_alert_failed(
                int(row["id"]), "tipo de notificacao WAN desconhecido"
            )
            return

        if not await ctx.notifier.send(message):
            ctx.db.mark_wan_alert_failed(int(row["id"]), "falha ao enviar")
            return
        ctx.db.mark_wan_alert_sent(int(row["id"]))


async def wan_notification_loop(ctx: ServerContext) -> None:
    """Reenvia alertas WAN pendentes sem aguardar o resumo diario."""
    log = logging.getLogger("server.wan_notify")
    while True:
        try:
            await drain_wan_notifications(ctx)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Erro ao processar notificacoes das WANs")
        await asyncio.sleep(WAN_NOTIFY_INTERVAL_SECONDS)


async def incident_loop(ctx: ServerContext) -> None:
    log = logging.getLogger("server.incidents")
    offline_alerted: dict[str, float] = {}
    while True:
        try:
            statuses = ctx.statuses()
            wans = ctx.wan_statuses()
            ctx.incidents.evaluate(statuses, wans)
            await drain_notifications(ctx)

            # Plano 19.3 - falha critica do proprio monitor (PDV sem reportar)
            if ctx.notifier.enabled:
                now = time.time()
                for machine, status in statuses.items():
                    age = status.get("seconds_since_last_seen")
                    if age is None or status.get("online"):
                        continue
                    if age < OFFLINE_ALERT_AFTER_SECONDS:
                        continue
                    if now - offline_alerted.get(machine, 0.0) < OFFLINE_ALERT_REPEAT_SECONDS:
                        continue
                    minutes = int(age // 60)
                    sent = await ctx.notifier.send(
                        ctx.notifier.format_monitor_failure(
                            f"{machine} sem enviar dados ha {minutes} min.\n"
                            f"Verificar se o caixa esta ligado e se o agente do monitor esta ativo."
                        )
                    )
                    if sent:
                        offline_alerted[machine] = now
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Erro no ciclo de incidentes")
        await asyncio.sleep(INCIDENT_INTERVAL_SECONDS)


async def notify_reconcile_loop(ctx: ServerContext) -> None:
    """Garante a entrega da outbox, inclusive o que ficou pendente."""
    log = logging.getLogger("server.notify")
    while True:
        try:
            await drain_notifications(ctx)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Erro ao processar a outbox de notificacoes")
        await asyncio.sleep(NOTIFY_INTERVAL_SECONDS)


async def retention_loop(ctx: ServerContext) -> None:
    log = logging.getLogger("server.retention")
    while True:
        try:
            removed = ctx.db.purge_old(ctx.settings.retention_days)
            if any(removed.values()):
                log.info("Retencao (%d dias) removeu: %s", ctx.settings.retention_days, removed)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Erro na rotina de retencao")
        await asyncio.sleep(24 * 3600)


async def daily_summary_loop(ctx: ServerContext) -> None:
    log = logging.getLogger("server.summary")
    target = None
    while True:
        if not (ctx.notifier.enabled and ctx.settings.telegram_daily_summary):
            target = None
            await asyncio.sleep(30)
            continue
        now = to_local(utc_now())
        configured_hour = ctx.settings.telegram_daily_summary_hour
        if target is None or target.hour != configured_hour:
            target = now.replace(hour=configured_hour, minute=0, second=0, microsecond=0)
            if target <= now:
                target = target + timedelta(days=1)
        await asyncio.sleep(min(60.0, max(1.0, (target - now).total_seconds())))
        if to_local(utc_now()) < target:
            continue
        try:
            statuses = ctx.statuses()
            availability = {
                machine: ctx.db.availability(machine, hours=24) for machine in statuses
            }
            period_start = to_iso(utc_now() - timedelta(hours=24))
            incidents = ctx.db.incidents_since(period_start)
            text = ctx.notifier.format_daily_summary(
                availability, ctx.db.wan_transitions(hours=24), incidents, list(statuses)
            )
            await ctx.notifier.send(text)
            target = target + timedelta(days=1)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Erro ao enviar o resumo diario")
            target = target + timedelta(days=1)


# ======================================================================
# Aplicacao
# ======================================================================
def create_app(settings: ServerSettings | None = None) -> FastAPI:
    settings = settings or ServerSettings.from_env()
    settings.ensure_dirs()
    setup_logging(settings.log_dir, settings.log_level, filename="server.log")
    log = logging.getLogger("server")

    templates = Jinja2Templates(directory=str(DASHBOARD_DIR / "templates"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not settings.agent_ingest_token:
            raise RuntimeError("AGENT_INGEST_TOKEN obrigatorio para iniciar a API")
        if not settings.allow_http and not (settings.tls_cert_file and settings.tls_key_file):
            raise RuntimeError("HTTPS obrigatorio: configure certificado e chave TLS")
        if not settings.allow_http and (
            not settings.tls_cert_file.is_file() or not settings.tls_key_file.is_file()
        ):
            raise RuntimeError("Os arquivos de certificado/chave TLS nao foram encontrados")
        db = Database(settings.db_path, logging.getLogger("server.db"))
        http = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        mikrotik = MikrotikService(settings)
        notifier = TelegramNotifier(settings, http)
        incidents = IncidentManager(db, settings)
        ctx = ServerContext(
            settings=settings,
            db=db,
            http=http,
            mikrotik=mikrotik,
            notifier=notifier,
            incidents=incidents,
        )
        app.state.ctx = ctx

        log.info(
            "%s no ar | banco=%s | mikrotik=%s | telegram=%s",
            C.APP_NAME,
            settings.db_path,
            "ativo" if mikrotik.enabled else "inativo",
            "ativo" if notifier.enabled else "inativo",
        )

        ctx.tasks.append(asyncio.create_task(incident_loop(ctx), name="incidents"))
        ctx.tasks.append(asyncio.create_task(notify_reconcile_loop(ctx), name="notify"))
        ctx.tasks.append(asyncio.create_task(wan_notification_loop(ctx), name="wan-notify"))
        ctx.tasks.append(asyncio.create_task(retention_loop(ctx), name="retention"))
        ctx.tasks.append(asyncio.create_task(daily_summary_loop(ctx), name="summary"))
        if mikrotik.enabled:
            ctx.tasks.append(asyncio.create_task(wan_loop(ctx), name="wan"))

        try:
            yield
        finally:
            log.info("Encerrando o servidor...")
            for task in ctx.tasks:
                task.cancel()
            await asyncio.gather(*ctx.tasks, return_exceptions=True)
            try:
                backup_dir = settings.data_dir / "backup"
                ctx.db.backup(backup_dir / f"bertolo-{utc_now().strftime('%Y%m%d-%H%M%S')}.db")
                log.info("Backup do banco gravado em %s", backup_dir)
            except Exception:  # noqa: BLE001
                log.warning("Nao foi possivel gravar o backup de encerramento", exc_info=True)
            await http.aclose()
            db.close()

    app = FastAPI(title=C.APP_NAME, version=C.SERVER_VERSION, lifespan=lifespan)
    app.state.admin_auth = AdminAuthStore(settings.data_dir / "admin-auth.json")
    app.state.admin_session_secret = secrets.token_bytes(32)
    app.state.admin_login_attempts = {}
    app.state.allow_http = settings.allow_http

    async def apply_server_settings(ctx: ServerContext, updates: dict[str, Any]) -> None:
        for key, value in updates.items():
            setattr(ctx.settings, key, value)
        ctx.notifier.settings = ctx.settings
        ctx.mikrotik.settings = ctx.settings
        ctx.incidents.settings = ctx.settings

        active_wan_tasks = [
            task for task in ctx.tasks if task.get_name() == "wan" and not task.done()
        ]
        if ctx.mikrotik.enabled and not active_wan_tasks:
            ctx.last_wan_snapshot = None
            ctx.tasks.append(asyncio.create_task(wan_loop(ctx), name="wan"))
        elif not ctx.mikrotik.enabled and active_wan_tasks:
            for task in active_wan_tasks:
                task.cancel()
                if task in ctx.tasks:
                    ctx.tasks.remove(task)
            await asyncio.gather(*active_wan_tasks, return_exceptions=True)
            ctx.last_wan_snapshot = None

    app.state.apply_server_settings = apply_server_settings

    @app.exception_handler(RequestValidationError)
    async def redact_validation_inputs(request: Request, exc: RequestValidationError):
        # Pydantic normalmente inclui o valor rejeitado em "input" e, em JSON
        # malformado, pode incluir o corpo inteiro. Remova esses dados para que
        # tokens e senhas nunca aparecam em respostas de erro.
        details = [
            {
                "loc": [str(part) for part in item.get("loc", ())],
                "msg": item.get("msg", "valor invalido"),
                "type": item.get("type", "value_error"),
            }
            for item in exc.errors()
        ]
        return JSONResponse(
            {"detail": details},
            status_code=422,
            headers={"Cache-Control": "no-store"},
        )

    @app.middleware("http")
    async def authenticate_agent_ingestion(request: Request, call_next):
        ingest_paths = {
            "/api/v1/measurements",
            "/api/v1/events",
            "/api/v1/sefaz-authorizations",
        }
        if request.method == "POST" and request.url.path in ingest_paths:
            expected = settings.agent_ingest_token
            scheme, _, token = request.headers.get("authorization", "").partition(" ")
            if (
                not expected
                or scheme.lower() != "bearer"
                or not hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))
            ):
                return JSONResponse(
                    {"detail": "token de agente ausente ou invalido"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)

    app.include_router(router)
    app.mount(
        "/static",
        StaticFiles(directory=str(DASHBOARD_DIR / "static")),
        name="static",
    )

    @app.get("/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        ctx: ServerContext = request.app.state.ctx
        counts = ctx.db.counts()
        wan = ctx.last_wan_snapshot
        return HealthResponse(
            status="ok",
            version=C.SERVER_VERSION,
            database="ok",
            database_path=str(ctx.settings.db_path),
            machines=counts["machines"],
            measurements=counts["measurements"],
            open_incidents=counts["open_incidents"],
            mikrotik_enabled=ctx.mikrotik.enabled,
            mikrotik_ok=wan.ok if wan else None,
            telegram_enabled=ctx.notifier.enabled,
            time_utc=utc_now(),
            time_local=format_local(utc_now()),
        )

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        ctx: ServerContext = request.app.state.ctx
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "title": ctx.settings.dashboard_title,
                "store_name": ctx.settings.store_name,
                "retention_days": ctx.settings.retention_days,
            },
        )

    @app.get("/configuracao", response_class=HTMLResponse)
    async def configuration(request: Request) -> HTMLResponse:
        ctx: ServerContext = request.app.state.ctx
        return templates.TemplateResponse(
            request,
            "configuration.html",
            {"title": "Configuração do HUB Monitor", "store_name": ctx.settings.store_name},
        )

    return app


app = create_app()


def _config_payload(settings: ServerSettings) -> dict[str, Any]:
    return {
        "store_name": settings.store_name,
        "host": settings.host,
        "port": settings.port,
        "https_configured": bool(settings.tls_cert_file and settings.tls_key_file),
        "local_subnet": settings.local_subnet,
        "db_path": str(settings.db_path),
        "data_dir": str(settings.data_dir),
        "log_dir": str(settings.log_dir),
        "retention_days": settings.retention_days,
        "incident_failure_threshold": settings.incident_failure_threshold,
        "incident_recovery_threshold": settings.incident_recovery_threshold,
        "telegram_enabled": settings.telegram_enabled,
        "telegram_daily_summary": settings.telegram_daily_summary,
        "mikrotik_enabled": settings.mikrotik_enabled,
        "mikrotik_host": settings.mikrotik_host,
        "mikrotik_user": settings.mikrotik_user,
        "mikrotik_wan_names": settings.mikrotik_wan_names,
        "env_file": str(settings.env_file) if settings.env_file else None,
    }


def run_backup(settings: ServerSettings) -> int:
    """Backup consistente do SQLite (seguro mesmo com o servidor no ar)."""
    settings.ensure_dirs()
    backup_dir = settings.data_dir / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    database = Database(settings.db_path)
    try:
        destination = backup_dir / f"bertolo-{utc_now().strftime('%Y%m%d-%H%M%S')}.db"
        database.backup(destination)
        print(str(destination))
    finally:
        database.close()

    # Mantem os 14 backups mais recentes
    backups = sorted(backup_dir.glob("bertolo-*.db"), key=lambda item: item.stat().st_mtime)
    for old in backups[:-14]:
        try:
            old.unlink()
        except OSError:
            pass
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bertolo-server", description="Servidor local HUB Monitoramento")
    parser.add_argument("--host", help="endereco de escuta (padrao: SERVER_HOST do .env)")
    parser.add_argument("--port", type=int, help="porta (padrao: SERVER_PORT do .env)")
    parser.add_argument("--print-config", action="store_true")
    parser.add_argument("--backup", action="store_true", help="grava um backup do banco e encerra")
    parser.add_argument("--generate-tls-cert", action="store_true", help="gera certificado local HTTPS")
    parser.add_argument("--tls-dir", help="pasta de destino dos arquivos PEM")
    parser.add_argument("--server-name", default="bertolo-server", help="nome DNS incluso no certificado")
    parser.add_argument("--server-ip", default="192.168.0.110", help="IP incluso no certificado")
    parser.add_argument("--version", action="version", version=C.SERVER_VERSION)
    args = parser.parse_args(argv)

    settings = ServerSettings.from_env()
    if args.generate_tls_cert:
        from server.tls import generate_local_certificate

        cert_dir = Path(args.tls_dir) if args.tls_dir else settings.base_dir / "certs"
        cert, key, trust = generate_local_certificate(cert_dir, args.server_name, args.server_ip)
        print(
            json.dumps(
                {"certificate": str(cert), "private_key": str(key), "trust_certificate": str(trust)}
            )
        )
        return 0
    if args.print_config:
        print(json.dumps(_config_payload(settings), ensure_ascii=False, indent=2))
        return 0

    if args.backup:
        return run_backup(settings)

    if not settings.agent_ingest_token:
        raise SystemExit("AGENT_INGEST_TOKEN obrigatorio. Configure o token antes de iniciar o servidor.")
    if not settings.allow_http and not (settings.tls_cert_file and settings.tls_key_file):
        raise SystemExit(
            "HTTPS obrigatorio: configure SERVER_TLS_CERT_FILE e SERVER_TLS_KEY_FILE "
            "(ou use SERVER_ALLOW_HTTP=true somente em desenvolvimento)."
        )
    if settings.tls_cert_file and not settings.tls_cert_file.is_file():
        raise SystemExit(f"Certificado TLS nao encontrado: {settings.tls_cert_file}")
    if settings.tls_key_file and not settings.tls_key_file.is_file():
        raise SystemExit(f"Chave privada TLS nao encontrada: {settings.tls_key_file}")

    application = create_app(settings)
    uvicorn.run(
        application,
        host=args.host or settings.host,
        port=args.port or settings.port,
        ssl_certfile=(str(settings.tls_cert_file) if not settings.allow_http and settings.tls_cert_file else None),
        ssl_keyfile=(str(settings.tls_key_file) if not settings.allow_http and settings.tls_key_file else None),
        log_config=None,
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
