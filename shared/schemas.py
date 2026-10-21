"""Contratos de dados entre agente e servidor (Pydantic v2)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.timeutil import utc_now

Severity = Literal["info", "warning", "critical"]
EventKind = Literal["state_change", "error", "info", "tef_connection", "monitor_error"]


class MachineInfo(BaseModel):
    """Identificacao da maquina (plano secao 6)."""

    model_config = ConfigDict(extra="ignore")

    machine_name: str
    hostname: str = ""
    local_ip: str = ""
    agent_version: str = ""
    os_version: str = ""
    collected_at: datetime = Field(default_factory=utc_now)

    @field_validator("machine_name")
    @classmethod
    def _upper(cls, value: str) -> str:
        value = (value or "").strip().upper()
        if not value:
            raise ValueError("machine_name e obrigatorio")
        return value


class Measurement(BaseModel):
    """Fotografia do estado de todos os componentes em um instante."""

    model_config = ConfigDict(extra="ignore")

    machine_name: str
    timestamp: datetime = Field(default_factory=utc_now)

    # Rede local
    gateway_ok: bool | None = None
    gateway_latency_ms: float | None = None
    gateway_loss_pct: float | None = None

    # Servidor Bertolo
    server_ok: bool | None = None
    server_latency_ms: float | None = None
    server_loss_pct: float | None = None

    # Internet geral
    internet_ok: bool | None = None
    internet_latency_ms: float | None = None
    internet_targets_ok: int | None = None
    internet_targets_total: int | None = None

    # DNS SEFAZ
    dns_ok: bool | None = None
    dns_latency_ms: float | None = None
    dns_resolver: str | None = None
    dns_system_ok: bool | None = None
    dns_external_ok: bool | None = None
    resolved_ips: list[str] = Field(default_factory=list)
    dns_error: str | None = None

    # SEFAZ TCP
    sefaz_tcp_ok: bool | None = None
    sefaz_tcp_latency_ms: float | None = None
    sefaz_tcp_ip: str | None = None
    sefaz_tcp_error: str | None = None

    # SEFAZ TLS
    sefaz_tls_ok: bool | None = None
    sefaz_tls_latency_ms: float | None = None
    sefaz_tls_protocol: str | None = None
    sefaz_cert_subject: str | None = None
    sefaz_cert_not_after: datetime | None = None
    sefaz_cert_days_left: int | None = None
    sefaz_tls_verify_ok: bool | None = None
    sefaz_tls_error: str | None = None

    # TEF - sem conteudo de sessao, sem dados de cartao
    tef_connected: bool | None = None
    tef_remote_ip: str | None = None
    tef_remote_port: int | None = None
    tef_connections: int | None = None
    tef_watch_ports: list[int] = Field(default_factory=list)

    # Contexto
    active_wan: str | None = None
    diagnosis: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("machine_name")
    @classmethod
    def _upper(cls, value: str) -> str:
        return (value or "").strip().upper()


class EventIn(BaseModel):
    """Evento pontual: transicao de estado, erro ou conexao TEF."""

    model_config = ConfigDict(extra="ignore")

    machine_name: str
    timestamp: datetime = Field(default_factory=utc_now)
    kind: EventKind = "info"
    component: str | None = None
    severity: Severity = "info"
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("machine_name")
    @classmethod
    def _upper(cls, value: str) -> str:
        return (value or "").strip().upper()


class MeasurementsIn(BaseModel):
    """Lote de medicoes enviado pelo agente."""

    model_config = ConfigDict(extra="ignore")

    machine: MachineInfo | None = None
    measurements: list[Measurement] = Field(default_factory=list)


class EventsIn(BaseModel):
    """Lote de eventos enviado pelo agente."""

    model_config = ConfigDict(extra="ignore")

    machine: MachineInfo | None = None
    events: list[EventIn] = Field(default_factory=list)


AuthorizationOutcome = Literal["authorized", "rejected", "error", "timeout", "unknown"]


class SefazAuthorization(BaseModel):
    """Resumo permitido de uma autorizacao observada nos logs do emissor."""

    model_config = ConfigDict(extra="ignore")

    event_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    machine_name: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int = Field(ge=0, le=86_400_000, strict=True)
    outcome: AuthorizationOutcome

    @field_validator("event_id")
    @classmethod
    def _event_id_is_not_access_key(cls, value: str) -> str:
        normalized = value.strip()
        if re.search(r"(?<!\d)\d{44}(?!\d)", normalized):
            raise ValueError("event_id nao pode ser uma chave de acesso NFC-e")
        return normalized

    @field_validator("machine_name")
    @classmethod
    def _upper_machine(cls, value: str) -> str:
        value = (value or "").strip().upper()
        if not value:
            raise ValueError("machine_name e obrigatorio")
        return value

    @field_validator("started_at", "completed_at")
    @classmethod
    def _timestamps_need_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp precisa informar fuso horario")
        return value

    @field_validator("completed_at")
    @classmethod
    def _completion_after_start(cls, value: datetime, info):
        started_at = info.data.get("started_at")
        if started_at is not None and value < started_at:
            raise ValueError("completed_at deve ser igual ou posterior a started_at")
        return value


class SefazAuthorizationsIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    machine: MachineInfo | None = None
    authorizations: list[SefazAuthorization] = Field(default_factory=list, max_length=1000)


class IngestResponse(BaseModel):
    received: int = 0
    stored: int = 0
    duplicates: int = 0
    rejected: int = 0


class MachineStatus(BaseModel):
    machine_name: str
    hostname: str = ""
    local_ip: str = ""
    agent_version: str = ""
    last_seen: datetime | None = None
    online: bool = False
    seconds_since_last_seen: float | None = None
    gateway_ok: bool | None = None
    gateway_latency_ms: float | None = None
    server_ok: bool | None = None
    server_latency_ms: float | None = None
    internet_ok: bool | None = None
    internet_latency_ms: float | None = None
    dns_ok: bool | None = None
    dns_latency_ms: float | None = None
    sefaz_tcp_ok: bool | None = None
    sefaz_tcp_latency_ms: float | None = None
    sefaz_tls_ok: bool | None = None
    sefaz_tls_latency_ms: float | None = None
    tef_connected: bool | None = None
    diagnosis: str | None = None
    active_wan: str | None = None
    updated_at: datetime | None = None


class WanStatus(BaseModel):
    timestamp: datetime | None = None
    wan_name: str
    provider: str = ""
    status: str = "unknown"
    probe: str | None = None
    latency_ms: float | None = None
    active_route: bool | None = None
    loss_pct: float | None = None


class IncidentOut(BaseModel):
    id: int
    type: str
    severity: str = "warning"
    started_at: datetime | None = None
    recovered_at: datetime | None = None
    duration_seconds: float | None = None
    affected_machines: list[str] = Field(default_factory=list)
    active_wan: str | None = None
    diagnosis: str | None = None
    telegram_sent: bool = False
    telegram_recovery_sent: bool = False
    open: bool = True


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "bertolo-monitor-server"
    version: str = ""
    database: str = "unknown"
    database_path: str = ""
    machines: int = 0
    measurements: int = 0
    open_incidents: int = 0
    mikrotik_enabled: bool = False
    mikrotik_ok: bool | None = None
    telegram_enabled: bool = False
    time_utc: datetime | None = None
    time_local: str = ""
