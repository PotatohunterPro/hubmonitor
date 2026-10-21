"""Monitores 7.5 e 7.6 - SEFAZ TCP e TLS.

O handshake TLS e feito sem enviar XML e sem qualquer chamada SOAP de
autorizacao, conforme o plano (secoes 4 e 7.6).
"""

from __future__ import annotations

import asyncio
import logging
import socket
import ssl
import time
from datetime import datetime, timezone

from agent.config import AgentSettings
from agent.monitors.base import CheckResult, Monitor
from agent.netprobe import tcp_connect
from agent.tlsutil import build_ssl_context
from shared import constants as C


class SefazTcpMonitor(Monitor):
    component = C.COMPONENT_SEFAZ_TCP

    def __init__(self, settings: AgentSettings) -> None:
        super().__init__(
            settings.intervals[C.COMPONENT_SEFAZ_TCP],
            logging.getLogger("agent.monitor.sefaz_tcp"),
        )
        self.settings = settings

    async def check(self) -> CheckResult:
        ok, latency, remote_ip, error = await tcp_connect(
            self.settings.sefaz_host,
            self.settings.sefaz_port,
            timeout=self.settings.tcp_timeout,
        )
        return CheckResult(
            component=self.component,
            ok=ok,
            latency_ms=latency,
            error=error,
            details={
                "host": self.settings.sefaz_host,
                "port": self.settings.sefaz_port,
                "remote_ip": remote_ip,
            },
        )


class SefazTlsMonitor(Monitor):
    component = C.COMPONENT_SEFAZ_TLS

    def __init__(self, settings: AgentSettings) -> None:
        super().__init__(
            settings.intervals[C.COMPONENT_SEFAZ_TLS],
            logging.getLogger("agent.monitor.sefaz_tls"),
        )
        self.settings = settings

    async def _handshake(self, verify: bool) -> tuple[bool, float | None, dict, str | None]:
        context = build_ssl_context(verify=verify)

        started = time.perf_counter()
        writer = None
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    self.settings.sefaz_host,
                    self.settings.sefaz_port,
                    ssl=context,
                    server_hostname=self.settings.sefaz_host,
                    family=socket.AF_INET,
                ),
                timeout=self.settings.tcp_timeout * 2,
            )
        except asyncio.TimeoutError:
            return False, None, {}, "timeout no handshake TLS"
        except ssl.SSLCertVerificationError as exc:
            return False, None, {}, f"certificado rejeitado: {exc.verify_message or exc}"
        except ssl.SSLError as exc:
            return False, None, {}, f"erro TLS: {exc}"
        except OSError as exc:
            return False, None, {}, f"{type(exc).__name__}: {exc}"

        latency = round((time.perf_counter() - started) * 1000.0, 1)
        info: dict = {}
        try:
            ssl_object = writer.get_extra_info("ssl_object")
            if ssl_object is not None:
                info["protocol"] = ssl_object.version()
                cipher = ssl_object.cipher()
                if cipher:
                    info["cipher"] = cipher[0]
                peer = writer.get_extra_info("peername")
                if peer:
                    info["remote_ip"] = peer[0]
                cert = ssl_object.getpeercert() or {}
                if cert:
                    info.update(_extract_certificate(cert))
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, RuntimeError):
                pass
        return True, latency, info, None

    async def check(self) -> CheckResult:
        ok, latency, info, error = await self._handshake(verify=True)

        if ok:
            verify_ok: bool | None = True
        elif error and error.startswith("certificado rejeitado"):
            # Repete sem validacao apenas para confirmar que o servico
            # responde; o certificado invalido continua sendo a falha.
            fallback_ok, _, fallback_info, _ = await self._handshake(verify=False)
            verify_ok = False
            if fallback_ok:
                info = fallback_info
                latency = latency if latency is not None else None
        else:
            verify_ok = None

        return CheckResult(
            component=self.component,
            ok=ok,
            latency_ms=latency if ok else None,
            error=error,
            details={
                "host": self.settings.sefaz_host,
                "port": self.settings.sefaz_port,
                "verify_ok": verify_ok,
                **info,
            },
        )


def _extract_certificate(cert: dict) -> dict:
    subject = ", ".join(
        f"{key}={value}" for rdn in cert.get("subject", ()) for key, value in rdn
    )
    issuer = ", ".join(f"{key}={value}" for rdn in cert.get("issuer", ()) for key, value in rdn)
    out: dict = {"cert_subject": subject or None, "cert_issuer": issuer or None}
    not_after_raw = cert.get("notAfter")
    if not_after_raw:
        try:
            timestamp = ssl.cert_time_to_seconds(not_after_raw)
            expires = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            out["cert_not_after"] = expires.isoformat()
            out["cert_days_left"] = (expires - datetime.now(timezone.utc)).days
        except (ValueError, OverflowError):
            out["cert_not_after_raw"] = not_after_raw
    return out
