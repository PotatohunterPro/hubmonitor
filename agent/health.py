"""Servidor HTTP local de health check.

Roda em uma thread separada em 127.0.0.1 e existe para:
  - o instalador PowerShell validar a instalacao;
  - o suporte tecnico inspecionar o estado sem abrir o log.
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

Provider = Callable[[], dict[str, Any]]


def _make_handler(provider: Provider, log: logging.Logger):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BertoloAgentHealth/1.0"

        def do_GET(self) -> None:  # noqa: N802 - assinatura da stdlib
            if self.path.split("?")[0] not in ("/health", "/", "/status"):
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'{"error":"not found"}')
                return
            try:
                body = json.dumps(provider(), ensure_ascii=False, default=str).encode("utf-8")
                self.send_response(200)
            except Exception as exc:  # noqa: BLE001
                log.exception("Falha ao montar o health")
                body = json.dumps({"status": "error", "error": str(exc)}).encode("utf-8")
                self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
            log.debug("health: " + fmt, *args)

    return Handler


class HealthServer:
    """Servidor de health em thread daemon."""

    def __init__(self, host: str, port: int, provider: Provider, logger: logging.Logger | None = None) -> None:
        self.host = host
        self.port = port
        self.provider = provider
        self.log = logger or logging.getLogger("agent.health")
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        try:
            self._server = ThreadingHTTPServer((self.host, self.port), _make_handler(self.provider, self.log))
        except OSError as exc:
            self.log.error("Nao foi possivel abrir o health em %s:%s - %s", self.host, self.port, exc)
            return False
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, name="agent-health", daemon=True)
        self._thread.start()
        self.log.info("Health local disponivel em http://%s:%s/health", self.host, self.port)
        return True

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
