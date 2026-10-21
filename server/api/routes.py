"""Rotas da API v1 - plano secao 10.

Fluxo obrigatorio: Agente -> API FastAPI -> Banco.
Os caixas nunca escrevem direto no SQLite.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import math
import re
import socket
import subprocess
import time
from dataclasses import replace
from datetime import timedelta

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response, Response
from pydantic import BaseModel, Field, SecretStr
from fastapi.responses import JSONResponse

from server.context import ServerContext
from server.services.admin_auth import (
    SESSION_MAX_AGE_SECONDS,
    AdminAuthStore,
    issue_session,
    valid_session,
)
from server.services.config_store import apply_windows_firewall_subnet, save_env_values
from server.services.diagnostics import machine_diagnosis
from server.services.mikrotik import MikrotikService
from shared import constants as C
from shared.schemas import (
    EventsIn,
    IngestResponse,
    MeasurementsIn,
    SefazAuthorizationsIn,
)
from shared.timeutil import parse_iso, to_iso, utc_now

router = APIRouter(prefix="/api/v1", tags=["bertolo-monitor"])
ADMIN_COOKIE = "hub_monitor_admin"


class AdminPasswordPayload(BaseModel):
    password: SecretStr


class AdminSettingsPayload(BaseModel):
    store_name: str = Field(min_length=1, max_length=80)
    local_subnet: str = Field(min_length=9, max_length=18)
    telegram_enabled: bool = False
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = Field(default="", max_length=64)
    mikrotik_enabled: bool = False
    mikrotik_host: str = Field(default="", max_length=64)
    mikrotik_port: int = Field(default=8728, ge=1, le=65535)
    mikrotik_user: str = Field(default="", max_length=64)
    mikrotik_password: SecretStr = SecretStr("")
    mikrotik_use_ssl: bool = False
    fiscal_uf: str = Field(default="", max_length=2)
    fiscal_document: str = Field(default="nfce", max_length=8)
    sefaz_host: str = Field(default="", max_length=253)
    sefaz_port: int = Field(default=443, ge=1, le=65535)
    fiscal_confirmed: bool = False


class TelegramTestPayload(BaseModel):
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = Field(min_length=1, max_length=64)


class MikrotikTestPayload(BaseModel):
    mikrotik_host: str = Field(min_length=1, max_length=64)
    mikrotik_port: int = Field(default=8728, ge=1, le=65535)
    mikrotik_user: str = Field(min_length=1, max_length=64)
    mikrotik_password: SecretStr
    mikrotik_use_ssl: bool = False


def _fiscal_from_settings(settings) -> dict | None:
    """Le o destino fiscal do .env do servidor (fonte de verdade persistida)."""
    from server.services.config_store import fiscal_target_from_settings

    target = fiscal_target_from_settings(settings)
    return target.to_dict() if target is not None else None


def get_context(request: Request) -> ServerContext:
    context = getattr(request.app.state, "ctx", None)
    if context is None:  # pragma: no cover - so ocorre em erro de boot
        raise HTTPException(status_code=503, detail="servidor inicializando")
    return context


def _is_local_server_request(request: Request) -> bool:
    host = request.client.host if request.client else ""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    if address.is_loopback:
        return True
    local_addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None):
            local_addresses.add(ipaddress.ip_address(item[4][0].split("%", 1)[0]))
    except (OSError, ValueError):
        pass
    return address in local_addresses


def _validate_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(status_code=403, detail="origem da solicitacao nao autorizada")


def _has_admin_session(request: Request) -> bool:
    secret: bytes = request.app.state.admin_session_secret
    store: AdminAuthStore = request.app.state.admin_auth
    return store.configured and valid_session(secret, request.cookies.get(ADMIN_COOKIE))


def _require_admin(request: Request) -> None:
    if not _has_admin_session(request):
        raise HTTPException(status_code=401, detail="entre com a senha administrativa")


def _set_admin_cookie(request: Request, response: Response) -> None:
    response.set_cookie(
        ADMIN_COOKIE,
        issue_session(request.app.state.admin_session_secret),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=not request.app.state.allow_http,
        samesite="strict",
        path="/",
    )


def _validate_private_subnet(value: str) -> str:
    try:
        network = ipaddress.IPv4Network(value, strict=False)
    except ValueError:
        raise HTTPException(status_code=422, detail="informe uma rede IPv4 em formato CIDR") from None
    if not network.is_private or network.prefixlen < 16 or network.prefixlen > 32:
        raise HTTPException(
            status_code=422,
            detail="use uma sub-rede privada IPv4 entre /16 e /32",
        )
    return str(network)


def _validate_telegram_chat_id(value: str) -> str:
    chat_id = value.strip()
    if not re.fullmatch(r"-?[0-9]{1,20}", chat_id):
        raise HTTPException(status_code=422, detail="informe o ID numerico do grupo do Telegram")
    return chat_id


def _validate_ipv4(value: str, label: str) -> str:
    try:
        return str(ipaddress.IPv4Address(value.strip()))
    except ipaddress.AddressValueError:
        raise HTTPException(status_code=422, detail=f"informe um IPv4 valido para {label}") from None


@router.get("/agent/check")
async def check_agent_connection(request: Request) -> JSONResponse:
    context = get_context(request)
    require_agent_token(request, context)
    return JSONResponse({"ok": True, "store_name": context.settings.store_name})


@router.get("/admin/status")
async def get_admin_status(request: Request) -> JSONResponse:
    store: AdminAuthStore = request.app.state.admin_auth
    return JSONResponse(
        {
            "configured": store.configured,
            "authenticated": _has_admin_session(request),
            "can_setup": _is_local_server_request(request) and not store.configured,
        }
    )


@router.post("/admin/setup")
async def setup_admin(payload: AdminPasswordPayload, request: Request) -> JSONResponse:
    _validate_same_origin(request)
    store: AdminAuthStore = request.app.state.admin_auth
    if not _is_local_server_request(request):
        raise HTTPException(
            status_code=403,
            detail="a primeira senha deve ser criada no proprio servidor da loja",
        )
    if store.configured:
        raise HTTPException(status_code=409, detail="a senha administrativa ja foi configurada")
    password = payload.password.get_secret_value()
    if not password or len(password) > 256:
        raise HTTPException(status_code=422, detail="senha administrativa invalida")
    try:
        store.create_password(password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except FileExistsError:
        raise HTTPException(status_code=409, detail="a senha administrativa ja foi configurada") from None
    response = JSONResponse({"ok": True})
    _set_admin_cookie(request, response)
    return response


@router.post("/admin/login")
async def login_admin(payload: AdminPasswordPayload, request: Request) -> JSONResponse:
    _validate_same_origin(request)
    store: AdminAuthStore = request.app.state.admin_auth
    if not store.configured:
        raise HTTPException(status_code=409, detail="configure a senha no proprio servidor da loja")
    password = payload.password.get_secret_value()
    if not password or len(password) > 256:
        raise HTTPException(status_code=422, detail="senha administrativa invalida")
    host = request.client.host if request.client else "unknown"
    attempts = request.app.state.admin_login_attempts
    now = time.monotonic()
    record = attempts.get(host, {"count": 0, "window": now, "locked_until": 0.0})
    if record["locked_until"] > now:
        raise HTTPException(status_code=429, detail="muitas tentativas; aguarde 15 minutos")
    if now - record["window"] >= 900:
        record = {"count": 0, "window": now, "locked_until": 0.0}
    if not store.verify_password(password):
        record["count"] += 1
        if record["count"] >= 5:
            record["locked_until"] = now + 900
        attempts[host] = record
        raise HTTPException(status_code=401, detail="senha incorreta")
    attempts.pop(host, None)
    response = JSONResponse({"ok": True})
    _set_admin_cookie(request, response)
    return response


@router.post("/admin/logout")
async def logout_admin(request: Request) -> JSONResponse:
    _validate_same_origin(request)
    response = JSONResponse({"ok": True})
    response.delete_cookie(ADMIN_COOKIE, path="/", samesite="strict")
    return response


@router.get("/admin/settings")
async def get_admin_settings(request: Request) -> JSONResponse:
    _require_admin(request)
    settings = get_context(request).settings
    fiscal_data = _fiscal_from_settings(settings)
    return JSONResponse(
        {
            "store_name": settings.store_name,
            "local_subnet": settings.local_subnet,
            "telegram_enabled": settings.telegram_enabled,
            "telegram_chat_id": settings.telegram_chat_id,
            "telegram_bot_configured": bool(settings.telegram_bot_token),
            "mikrotik_enabled": settings.mikrotik_enabled,
            "mikrotik_host": settings.mikrotik_host,
            "mikrotik_port": settings.mikrotik_port,
            "mikrotik_user": settings.mikrotik_user,
            "mikrotik_password_configured": bool(settings.mikrotik_password),
            "mikrotik_use_ssl": settings.mikrotik_use_ssl,
            "fiscal_configured": fiscal_data is not None,
            "fiscal_uf": (fiscal_data or {}).get("uf", ""),
            "fiscal_document": (fiscal_data or {}).get("document", ""),
            "sefaz_host": (fiscal_data or {}).get("host", ""),
            "sefaz_port": (fiscal_data or {}).get("port", 443),
            "fiscal_confirmed": (fiscal_data or {}).get("confirmed", False),
        }
    )


@router.get("/admin/connection-file")
async def download_connection_file(request: Request) -> Response:
    """Entrega o .hubconn da loja para o operador salvar e distribuir."""
    import json
    import re

    _require_admin(request)
    settings = get_context(request).settings

    from server.services.connection_export import build_store_connection

    try:
        data = build_store_connection(settings)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    slug = re.sub(r"[^A-Za-z0-9]+", "-", settings.store_name or "loja").strip("-").lower() or "loja"
    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{slug}.hubconn"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/admin/agent-token")
async def get_agent_token(request: Request) -> JSONResponse:
    _require_admin(request)
    settings = get_context(request).settings
    if not settings.agent_ingest_token:
        raise HTTPException(status_code=503, detail="a credencial dos caixas nao esta configurada")
    return JSONResponse(
        {"agent_ingest_token": settings.agent_ingest_token},
        headers={"Cache-Control": "no-store"},
    )


@router.put("/admin/settings")
async def update_admin_settings(
    payload: AdminSettingsPayload, request: Request
) -> JSONResponse:
    _validate_same_origin(request)
    _require_admin(request)
    context = get_context(request)
    settings = context.settings
    store_name = payload.store_name.strip()
    if not store_name:
        raise HTTPException(status_code=422, detail="informe o nome da loja")
    local_subnet = _validate_private_subnet(payload.local_subnet)

    if payload.telegram_enabled:
        token = payload.telegram_bot_token.get_secret_value().strip() or settings.telegram_bot_token
        if len(token) > 256:
            raise HTTPException(status_code=422, detail="token do bot invalido")
        chat_id = _validate_telegram_chat_id(payload.telegram_chat_id)
        if not token:
            raise HTTPException(status_code=422, detail="informe o token do bot do Telegram")
    else:
        token = ""
        chat_id = ""

    mikrotik_host = settings.mikrotik_host
    mikrotik_user = settings.mikrotik_user
    mikrotik_password = settings.mikrotik_password
    if payload.mikrotik_enabled:
        mikrotik_host = _validate_ipv4(payload.mikrotik_host, "MikroTik")
        mikrotik_user = payload.mikrotik_user.strip()
        mikrotik_password = payload.mikrotik_password.get_secret_value().strip() or settings.mikrotik_password
        if len(mikrotik_password) > 256:
            raise HTTPException(status_code=422, detail="senha da MikroTik invalida")
        if not mikrotik_user or not mikrotik_password:
            raise HTTPException(
                status_code=422,
                detail="informe o usuario e a senha de leitura da MikroTik",
            )

    env_updates = {
        "STORE_NAME": store_name,
        "LOCAL_SUBNET": local_subnet,
        "TELEGRAM_BOT_TOKEN": token,
        "TELEGRAM_CHAT_ID": chat_id,
        "MIKROTIK_ENABLED": str(payload.mikrotik_enabled).lower(),
        "MIKROTIK_HOST": mikrotik_host,
        "MIKROTIK_PORT": str(payload.mikrotik_port),
        "MIKROTIK_USER": mikrotik_user,
        "MIKROTIK_PASSWORD": mikrotik_password,
        "MIKROTIK_USE_SSL": str(payload.mikrotik_use_ssl).lower(),
    }
    from shared import fiscal as fiscal_mod

    fiscal_target = None
    if payload.sefaz_host.strip():
        try:
            fiscal_target = fiscal_mod.validate_target(
                uf=payload.fiscal_uf,
                document=payload.fiscal_document,
                host=payload.sefaz_host,
                port=payload.sefaz_port,
                confirmed=payload.fiscal_confirmed,
            )
        except fiscal_mod.FiscalConfigError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        env_updates.update(fiscal_mod.env_values(fiscal_target))

    anterior = _fiscal_from_settings(settings) or {}
    fiscal_changed = bool(
        payload.sefaz_host.strip()
        and (
            payload.sefaz_host.strip() != (anterior.get("host") or "")
            or payload.sefaz_port != int(anterior.get("port") or 0)
            or (payload.fiscal_uf or "") != (anterior.get("uf") or "")
            or (payload.fiscal_document or "nfce") != (anterior.get("document") or "")
        )
    )

    firewall_changed = False
    try:
        if local_subnet != settings.local_subnet:
            apply_windows_firewall_subnet(local_subnet, settings.port)
            firewall_changed = True
        save_env_values(settings.env_file, env_updates)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        if firewall_changed:
            try:
                apply_windows_firewall_subnet(settings.local_subnet, settings.port)
            except (OSError, subprocess.SubprocessError):
                pass
        detail = str(exc) if isinstance(exc, ValueError) else "nao foi possivel salvar com seguranca"
        raise HTTPException(status_code=500, detail=detail) from None

    await request.app.state.apply_server_settings(
        context,
        {
            "store_name": store_name,
            "local_subnet": local_subnet,
            "telegram_bot_token": token,
            "telegram_chat_id": chat_id,
            "telegram_enabled": bool(token and chat_id),
            "mikrotik_enabled": payload.mikrotik_enabled,
            "mikrotik_host": mikrotik_host,
            "mikrotik_port": payload.mikrotik_port,
            "mikrotik_user": mikrotik_user,
            "mikrotik_password": mikrotik_password,
            "mikrotik_use_ssl": payload.mikrotik_use_ssl,
        },
    )
    if fiscal_changed:
        # O agente local precisa reler o .env para vigiar o novo destino.
        try:
            from server.services.config_store import restart_local_agent

            restart_local_agent()
        except Exception:  # noqa: BLE001 - reiniciar e best-effort
            pass
    return JSONResponse({"ok": True, "message": "Configuracoes salvas e aplicadas."})


class FiscalTestPayload(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=443, ge=1, le=65535)


@router.get("/admin/fiscal/options")
async def get_fiscal_options(request: Request) -> JSONResponse:
    from shared import fiscal as fiscal_mod

    _require_admin(request)
    return JSONResponse({"ufs": fiscal_mod.options(), "documents": fiscal_mod.DOCUMENTS})


@router.post("/admin/fiscal/test")
async def test_fiscal_endpoint(payload: FiscalTestPayload, request: Request) -> JSONResponse:
    from fastapi.concurrency import run_in_threadpool

    from shared import fiscal as fiscal_mod

    _validate_same_origin(request)
    _require_admin(request)
    try:
        host = fiscal_mod.normalize_host(payload.host)
    except fiscal_mod.FiscalConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    result = await run_in_threadpool(fiscal_mod.probe, host, payload.port)
    return JSONResponse(result, status_code=200 if result["ok"] else 502)


@router.post("/admin/telegram/test")
async def test_telegram(payload: TelegramTestPayload, request: Request) -> JSONResponse:
    _validate_same_origin(request)
    _require_admin(request)
    context = get_context(request)
    token = payload.telegram_bot_token.get_secret_value().strip() or context.settings.telegram_bot_token
    chat_id = _validate_telegram_chat_id(payload.telegram_chat_id)
    if not token:
        raise HTTPException(status_code=422, detail="informe o token do bot do Telegram")
    if len(token) > 256:
        raise HTTPException(status_code=422, detail="token do bot invalido")

    try:
        identity_response = await context.http.get(
            f"https://api.telegram.org/bot{token}/getMe", timeout=15.0
        )
        identity = identity_response.json()
    except (httpx.RequestError, ValueError):
        raise HTTPException(
            status_code=502,
            detail="nao foi possivel acessar o Telegram; confira a internet do servidor",
        ) from None
    if identity_response.status_code == 401:
        raise HTTPException(status_code=422, detail="token do bot invalido; confira o BotFather")
    if identity_response.status_code >= 500:
        raise HTTPException(status_code=502, detail="o Telegram esta temporariamente indisponivel; tente novamente")
    if identity_response.status_code >= 400 or not identity.get("ok"):
        raise HTTPException(status_code=422, detail="token do bot invalido; confira o BotFather")

    try:
        message_response = await context.http.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": "HUB Monitor: teste de configuracao confirmado.",
                "disable_web_page_preview": True,
            },
            timeout=15.0,
        )
        message = message_response.json()
    except (httpx.RequestError, ValueError):
        raise HTTPException(
            status_code=502,
            detail="nao foi possivel enviar a mensagem; verifique a internet do servidor",
        ) from None
    if message_response.status_code >= 500:
        raise HTTPException(status_code=502, detail="o Telegram esta temporariamente indisponivel; tente novamente")
    if message_response.status_code >= 400 or not message.get("ok"):
        raise HTTPException(
            status_code=422,
            detail="bot validado, mas nao enviou ao grupo; confira o ID e adicione o bot ao grupo",
        )
    bot = identity.get("result") or {}
    return JSONResponse(
        {
            "ok": True,
            "bot_id": bot.get("id"),
            "bot_username": bot.get("username"),
            "message": "Mensagem de teste enviada ao grupo.",
        }
    )


@router.post("/admin/mikrotik/test")
async def test_mikrotik(payload: MikrotikTestPayload, request: Request) -> JSONResponse:
    _validate_same_origin(request)
    _require_admin(request)
    context = get_context(request)
    host = _validate_ipv4(payload.mikrotik_host, "MikroTik")
    password = payload.mikrotik_password.get_secret_value().strip()
    password = password or context.settings.mikrotik_password
    if not password:
        raise HTTPException(status_code=422, detail="informe a senha de leitura da MikroTik")
    candidate = replace(
        context.settings,
        mikrotik_enabled=True,
        mikrotik_host=host,
        mikrotik_port=payload.mikrotik_port,
        mikrotik_user=payload.mikrotik_user.strip(),
        mikrotik_password=password,
        mikrotik_use_ssl=payload.mikrotik_use_ssl,
    )
    snapshot = await MikrotikService(candidate).poll()
    if not snapshot.ok:
        raise HTTPException(
            status_code=422,
            detail="sem resposta da MikroTik; confira IP, porta, credenciais e permissao somente leitura",
        )
    return JSONResponse({"ok": True, "message": "MikroTik respondeu usando consultas de leitura."})


def require_agent_token(request: Request, context: ServerContext) -> None:
    expected = context.settings.agent_ingest_token
    supplied = request.headers.get("authorization", "")
    scheme, _, token = supplied.partition(" ")
    if (
        not expected
        or scheme.lower() != "bearer"
        or not hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))
    ):
        raise HTTPException(
            status_code=401,
            detail="token de agente ausente ou invalido",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/measurements", response_model=IngestResponse)
async def post_measurements(payload: MeasurementsIn, request: Request) -> IngestResponse:
    context = get_context(request)
    require_agent_token(request, context)
    context.db.upsert_machine(payload.machine)

    active_wan = context.active_wan_name()
    items = []
    for measurement in payload.measurements:
        # Agentes anteriores podem reenviar snapshots enfileirados quando TEF
        # ainda estava ativo. Preserve o historico de rede sem reintroduzir TEF.
        measurement.tef_connected = None
        measurement.tef_remote_ip = None
        measurement.tef_remote_port = None
        measurement.tef_connections = None
        measurement.tef_watch_ports = []
        measurement.diagnosis = machine_diagnosis(measurement.model_dump())
        if measurement.active_wan is None:
            measurement.active_wan = active_wan
        items.append(measurement)

    stored, duplicates = context.db.insert_measurements(items)
    return IngestResponse(
        received=len(payload.measurements), stored=stored, duplicates=duplicates
    )


@router.post("/events", response_model=IngestResponse)
async def post_events(payload: EventsIn, request: Request) -> IngestResponse:
    context = get_context(request)
    require_agent_token(request, context)
    context.db.upsert_machine(payload.machine)
    events = [
        event
        for event in payload.events
        if event.component != C.COMPONENT_TEF and event.kind != "tef_connection"
    ]
    stored, duplicates = context.db.insert_events(events)
    return IngestResponse(
        received=len(payload.events),
        stored=stored,
        duplicates=duplicates,
        rejected=len(payload.events) - len(events),
    )


@router.post("/sefaz-authorizations", response_model=IngestResponse)
async def post_sefaz_authorizations(
    payload: SefazAuthorizationsIn, request: Request
) -> IngestResponse:
    context = get_context(request)
    require_agent_token(request, context)
    context.db.upsert_machine(payload.machine)
    stored, duplicates = context.db.insert_sefaz_authorizations(payload.authorizations)
    return IngestResponse(
        received=len(payload.authorizations), stored=stored, duplicates=duplicates
    )


@router.get("/machines/{machine}/sefaz-authorizations")
async def get_sefaz_authorizations(
    machine: str,
    request: Request,
    hours: int = Query(default=24, ge=1, le=720),
) -> JSONResponse:
    context = get_context(request)
    rows = context.db.sefaz_authorization_history(machine, hours=hours)
    latest = context.db.latest_measurements().get(machine.upper(), {})
    try:
        latest_details = json.loads(latest.get("details") or "{}")
    except (TypeError, ValueError):
        latest_details = {}
    log_status = latest_details.get("sefaz_authorization_log") or {}
    available = bool(log_status.get("configured") and log_status.get("available"))

    durations = sorted(int(row["duration_ms"]) for row in rows)
    summary = {
        "count": len(durations),
        "p50_ms": _percentile(durations, 0.50),
        "p95_ms": _percentile(durations, 0.95),
        "slow_count": sum(value >= 5000 for value in durations),
    }
    authorizations = []
    network_components = ("gateway", "internet", "sefaz_tcp", "sefaz_tls")
    for row in rows:
        start = parse_iso(row["started_at"])
        end = parse_iso(row["completed_at"])
        midpoint = start + (end - start) / 2 if start and end else start
        measurement = (
            context.db.nearest_measurement(machine, to_iso(midpoint)) if midpoint else None
        )
        checks: dict = {}
        if measurement:
            try:
                details = json.loads(measurement.get("details") or "{}")
                checks = details.get("checks") or {}
            except (TypeError, ValueError):
                checks = {}
        network = {}
        for component in network_components:
            sample = checks.get(component) or {}
            checked_at = parse_iso(sample.get("checked_at"))
            in_window = bool(
                checked_at
                and start
                and end
                and start - timedelta(seconds=60)
                <= checked_at
                <= end + timedelta(seconds=60)
            )
            network[component] = {
                "ok": sample.get("ok") if in_window else None,
                "latency_ms": sample.get("latency_ms") if in_window else None,
                "checked_at": to_iso(checked_at) if in_window else None,
            }
        known = [network[name]["ok"] for name in network_components]
        if any(value is False for value in known):
            diagnosis = "falha de rede observada na janela da emissao"
        elif all(value is True for value in known):
            diagnosis = C.DIAG_AUTH_AFTER_CONNECTION
        else:
            diagnosis = "dados de rede insuficientes para localizar a demora"

        authorizations.append(
            {
                "event_id": row["event_id"],
                "machine_name": row["machine_name"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "duration_ms": row["duration_ms"],
                "outcome": row["outcome"],
                "network": network,
                "network_measurement_at": measurement.get("timestamp") if measurement else None,
                "diagnosis": diagnosis,
            }
        )
    return JSONResponse(
        {
            "machine_name": machine.upper(),
            "hours": hours,
            "available": available,
            "count": len(authorizations),
            "summary": summary,
            "authorizations": authorizations,
        }
    )


@router.get("/status")
async def get_status(request: Request) -> JSONResponse:
    context = get_context(request)
    return JSONResponse(context.serialize_status())


@router.get("/machines")
async def get_machines(request: Request) -> JSONResponse:
    context = get_context(request)
    statuses = context.serialize_status()["machines"]
    return JSONResponse(statuses)


@router.get("/machines/{machine}/history")
async def get_machine_history(
    machine: str,
    request: Request,
    hours: int = Query(default=6, ge=1, le=720),
    limit: int = Query(default=3000, ge=1, le=20000),
) -> JSONResponse:
    context = get_context(request)
    rows = context.db.machine_history(machine, hours=hours, limit=limit)
    for row in rows:
        row["resolved_ips"] = _json_list(row.get("resolved_ips"))
        row["details"] = None  # nao faz sentido despejar o detalhe completo no grafico
        for tef_field in (
            "tef_connected", "tef_remote_ip", "tef_remote_port", "tef_connections"
        ):
            row.pop(tef_field, None)
    return JSONResponse(
        {
            "machine_name": machine.upper(),
            "hours": hours,
            "count": len(rows),
            "availability": context.db.availability(machine, hours=hours),
            "measurements": rows,
        }
    )


@router.get("/machines/{machine}/availability")
async def get_availability(
    machine: str, request: Request, hours: int = Query(default=24, ge=1, le=720)
) -> JSONResponse:
    context = get_context(request)
    return JSONResponse(context.db.availability(machine, hours=hours))


@router.get("/events")
async def get_events(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    machine: str | None = None,
) -> JSONResponse:
    context = get_context(request)
    rows = context.db.recent_events(limit=limit, machine=machine)
    for row in rows:
        row["payload"] = None
    return JSONResponse(rows)


@router.get("/incidents")
async def get_incidents(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    only_open: bool = False,
) -> JSONResponse:
    context = get_context(request)
    return JSONResponse(context.db.list_incidents(limit=limit, only_open=only_open))


@router.get("/wans")
async def get_wans(request: Request) -> JSONResponse:
    context = get_context(request)
    return JSONResponse(
        {
            "active_wan": context.active_wan_name(),
            "wans": context.wan_statuses(),
            "mikrotik": context.mikrotik.status_payload(),
            "checked_at": to_iso(utc_now()),
        }
    )


def _json_list(value: object) -> list:
    import json

    if not value:
        return []
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return []


def _parse_or_none(value: object):
    return parse_iso(value) if isinstance(value, str) else None


def _percentile(values: list[int], percentile: float) -> float | None:
    if not values:
        return None
    position = (len(values) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(values[lower])
    weight = position - lower
    return round(values[lower] * (1 - weight) + values[upper] * weight, 1)
