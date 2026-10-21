"""Sondas de rede multiplataforma (Windows, macOS e Linux).

Usa o utilitario ping do sistema operacional. Isso evita depender de
socket bruto (que exige privilegio) e funciona igual em PDV Windows e
em maquina de desenvolvimento macOS/Linux.

O parse e tolerante a saida localizada (Time= / tempo= / Zeit=).
"""

from __future__ import annotations

import asyncio
import platform
import re
import time
from dataclasses import dataclass

MS_RE = re.compile(r"[=<]\s*([0-9]+(?:[.,][0-9]+)?)\s*ms", re.IGNORECASE)
PACKET_LOSS_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)%\s*(?:packet\s+)?loss", re.IGNORECASE)
TTL_RE = re.compile(r"ttl[=:]\s*\d+", re.IGNORECASE)

_SYSTEM = platform.system().lower()


@dataclass(slots=True)
class PingResult:
    host: str
    ok: bool
    latency_ms: float | None = None
    loss_pct: float | None = None
    error: str | None = None


def _ping_command(host: str, timeout_ms: int) -> list[str]:
    seconds = max(1, int((timeout_ms + 999) // 1000))
    if _SYSTEM.startswith("win"):
        return ["ping", "-n", "1", "-w", str(timeout_ms), host]
    if _SYSTEM == "darwin":
        return ["ping", "-c", "1", "-t", str(seconds), host]
    return ["ping", "-c", "1", "-W", str(seconds), host]


async def ping_once(host: str, timeout_ms: int = 1500) -> PingResult:
    """Executa um unico ping e devolve latencia/perda."""
    started = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_exec(
            *_ping_command(host, timeout_ms),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except (OSError, ValueError) as exc:
        return PingResult(host, False, loss_pct=100.0, error=f"ping indisponivel: {exc}")

    try:
        stdout, _ = await asyncio.wait_for(
            proc.communicate(), timeout=(timeout_ms / 1000.0) + 2.0
        )
    except asyncio.TimeoutError:
        with_suppress(proc)
        return PingResult(host, False, loss_pct=100.0, error="timeout")

    text = (stdout or b"").decode("utf-8", errors="replace")
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    if proc.returncode != 0 and not TTL_RE.search(text):
        return PingResult(host, False, loss_pct=100.0, error=_describe_failure(text))

    match = MS_RE.search(text)
    if match:
        latency = float(match.group(1).replace(",", "."))
        return PingResult(host, True, latency_ms=latency, loss_pct=0.0)

    if TTL_RE.search(text):
        return PingResult(host, True, latency_ms=round(elapsed_ms, 1), loss_pct=0.0)

    return PingResult(host, False, loss_pct=100.0, error=_describe_failure(text))


def with_suppress(proc: asyncio.subprocess.Process) -> None:
    try:
        proc.kill()
    except ProcessLookupError:
        pass


def _describe_failure(text: str) -> str:
    """Extrai uma causa legivel da saida do ping, tolerante ao idioma."""
    loss = PACKET_LOSS_RE.search(text)
    for raw_line in text.splitlines():
        line = raw_line.strip()
        low = line.lower()
        if not low:
            continue
        if "loss" in low and "100" in low:
            return "100% de perda de pacotes (sem resposta)"
        if "request timeout" in low or "timed out" in low or "timeout" in low:
            return "timeout na resposta"
        if "unreachable" in low or "inalcancavel" in low or "inacessivel" in low:
            return line[:200]
        if "could not find host" in low or "unknown host" in low or "nome desconhecido" in low:
            return line[:200]
    if loss:
        return loss.group(1).replace(",", ".") + "% de perda de pacotes"
    return "sem resposta"


async def tcp_connect(
    host: str, port: int, timeout: float = 3.0
) -> tuple[bool, float | None, str | None, str | None]:
    """Abre uma conexao TCP IPv4.

    Retorna (ok, latencia_ms, ip_remoto, erro).
    """
    started = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, family=socket_family_inet()), timeout=timeout
        )
    except asyncio.TimeoutError:
        return False, None, None, f"timeout apos {timeout:.1f}s"
    except OSError as exc:
        return False, None, None, f"{type(exc).__name__}: {exc}"

    latency = (time.perf_counter() - started) * 1000.0
    remote_ip = None
    try:
        peer = writer.get_extra_info("peername")
        if peer:
            remote_ip = peer[0]
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, RuntimeError):
            pass
    return True, round(latency, 1), remote_ip, None


def socket_family_inet() -> int:
    import socket

    return socket.AF_INET
