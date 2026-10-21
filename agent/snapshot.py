"""Montagem da fotografia (Measurement) a partir do estado dos monitores."""

from __future__ import annotations

from typing import Any

from agent.monitors.base import Monitor
from shared import constants as C
from shared.schemas import Measurement
from shared.timeutil import parse_iso, utc_now


def _last(monitors: dict[str, Monitor], component: str):
    monitor = monitors.get(component)
    return monitor.last if monitor else None


def build_measurement(machine_name: str, monitors: dict[str, Monitor]) -> Measurement:
    measurement = Measurement(machine_name=machine_name, timestamp=utc_now())

    gateway = _last(monitors, C.COMPONENT_GATEWAY)
    if gateway:
        measurement.gateway_ok = gateway.ok
        measurement.gateway_latency_ms = gateway.latency_ms
        measurement.gateway_loss_pct = _as_float(gateway.details.get("loss_pct"))

    server = _last(monitors, C.COMPONENT_SERVER)
    if server:
        measurement.server_ok = server.ok
        measurement.server_latency_ms = server.latency_ms
        measurement.server_loss_pct = _as_float(server.details.get("loss_pct"))

    internet = _last(monitors, C.COMPONENT_INTERNET)
    if internet:
        measurement.internet_ok = internet.ok
        measurement.internet_latency_ms = internet.latency_ms
        measurement.internet_targets_ok = _as_int(internet.details.get("targets_ok"))
        measurement.internet_targets_total = _as_int(internet.details.get("targets_total"))

    dns = _last(monitors, C.COMPONENT_DNS)
    if dns:
        measurement.dns_ok = dns.ok
        measurement.dns_latency_ms = dns.latency_ms
        measurement.dns_resolver = dns.details.get("resolver")
        measurement.dns_system_ok = dns.details.get("system_ok")
        measurement.dns_external_ok = dns.details.get("external_ok")
        measurement.resolved_ips = list(dns.details.get("resolved_ips") or [])
        measurement.dns_error = dns.error

    sefaz_tcp = _last(monitors, C.COMPONENT_SEFAZ_TCP)
    if sefaz_tcp:
        measurement.sefaz_tcp_ok = sefaz_tcp.ok
        measurement.sefaz_tcp_latency_ms = sefaz_tcp.latency_ms
        measurement.sefaz_tcp_ip = sefaz_tcp.details.get("remote_ip")
        measurement.sefaz_tcp_error = sefaz_tcp.error

    sefaz_tls = _last(monitors, C.COMPONENT_SEFAZ_TLS)
    if sefaz_tls:
        measurement.sefaz_tls_ok = sefaz_tls.ok
        measurement.sefaz_tls_latency_ms = sefaz_tls.latency_ms
        measurement.sefaz_tls_protocol = sefaz_tls.details.get("protocol")
        measurement.sefaz_cert_subject = sefaz_tls.details.get("cert_subject")
        measurement.sefaz_cert_not_after = parse_iso(sefaz_tls.details.get("cert_not_after"))
        measurement.sefaz_cert_days_left = _as_int(sefaz_tls.details.get("cert_days_left"))
        measurement.sefaz_tls_verify_ok = sefaz_tls.details.get("verify_ok")
        measurement.sefaz_tls_error = sefaz_tls.error

    checks = {
        name: {
            "checked_at": monitor.last.checked_at,
            "ok": monitor.last.ok,
            "latency_ms": monitor.last.latency_ms,
        }
        for name, monitor in monitors.items()
        if monitor.last is not None
    }
    measurement.details = {
        "checks": checks,
        "monitors": {name: monitor.snapshot() for name, monitor in monitors.items()},
    }
    return measurement


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
