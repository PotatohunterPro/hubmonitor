"""Janela e bandeja do HUB Monitoramento.

Este e o processo da sessao do usuario. Ele NAO coleta dados: apenas
apresenta o estado e chama a API local. Fechar a janela, sair pela
bandeja ou encerrar a sessao nao interrompe a coleta, que roda no
servico do Windows.

Modos:
    HUBMonitor.exe ui            abre janela + bandeja
    HUBMonitor.exe ui --tray-only  inicia minimizado na bandeja
    HUBMonitor.exe ui --print-status  imprime o estado em JSON (suporte)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:  # pragma: no cover - dependencia de GUI
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

from shared.connection_file import read_connection, write_connection

try:  # pragma: no cover
    import webview
except ImportError:  # pragma: no cover
    webview = None

try:  # pragma: no cover
    import pystray
    from PIL import Image
except ImportError:  # pragma: no cover
    pystray = None
    Image = None

ROLE_FILE = "role.json"
UI_FILE = Path(__file__).resolve().parent / "ui" / "index.html"
ICON_FILE = Path(__file__).resolve().parent / "ui" / "hubmonitor.png"
REFRESH_SECONDS = 10.0


def state_dir() -> Path:
    base = os.environ.get("PROGRAMDATA")
    if base:
        return Path(base) / "HUBMonitor"
    return Path.home() / ".hubmonitor"


def load_role() -> dict[str, Any]:
    path = state_dir() / ROLE_FILE
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
    return {
        "mode": "agent",
        "api_url": "http://127.0.0.1:8010",
        "service_name": "HUBMonitorAgent",
    }


STATE_LABELS = {"ok": "normal", "fail": "falha", "unknown": "sem dados"}


def panel_url(role: dict[str, Any]) -> str | None:
    """URL do painel da loja para o modo atual.

    Servidor: a propria API. Agente: o endereco HTTPS vindo do arquivo de
    conexao importado (o painel e o do servidor da loja).
    """
    if str(role.get("mode") or "agent") == "server":
        base = str(role.get("api_url") or "").rstrip("/")
        return base + "/" if base else None

    path = state_dir() / "connection.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    base = str(data.get("base_url") or "").rstrip("/")
    return base + "/" if base else None


def _http_get(url: str, ca_file: str | None) -> dict[str, Any]:
    if httpx is None:
        raise RuntimeError("httpx nao instalado")
    verify: Any = True
    if url.startswith("https://"):
        if not ca_file or not Path(ca_file).is_file():
            raise RuntimeError("certificado da loja ausente; conexao HTTPS nao validada")
        verify = ca_file
    with httpx.Client(verify=verify, timeout=8.0) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def _state(value: Any) -> str:
    if value is True:
        return "ok"
    if value is False:
        return "fail"
    return "unknown"


def collect_status(role: dict[str, Any]) -> dict[str, Any]:
    """Monta o modelo exibido na janela. Nunca levanta excecao."""
    mode = str(role.get("mode") or "agent")
    api_url = str(role.get("api_url") or "http://127.0.0.1:8010").rstrip("/")
    ca_file = role.get("ca_file")

    result: dict[str, Any] = {
        "mode": mode,
        "store": role.get("store_name") or "HUB Monitoramento",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": [],
        "occurrences": [],
        "machines": [],
        "error": None,
    }

    try:
        if mode == "server":
            payload = _http_get(api_url + "/api/v1/status", ca_file)
            result["store"] = payload.get("store_name") or result["store"]
            machines = payload.get("machines") or []
            online = [item for item in machines if item.get("online")]
            # O pedido exige ver, no servidor, os computadores cadastrados
            # e a ultima comunicacao de cada um.
            result["machines"] = [
                {
                    "name": str(item.get("machine_name") or "?"),
                    "state": "ok" if item.get("online") else "fail",
                    "last_seen": str(item.get("last_seen") or ""),
                    "detail": str(item.get("diagnosis") or ""),
                }
                for item in machines
            ]
            result["items"] = [
                {
                    "label": "Internet",
                    "state": _state(all(item.get("internet_ok") for item in online) if online else None),
                    "detail": f"{len(online)} de {len(machines)} computadores comunicando",
                },
                {
                    "label": "Acesso à SEFAZ",
                    "state": _state(all(item.get("sefaz_tcp_ok") for item in online) if online else None),
                    "detail": "teste de conexão TCP/TLS, nao confirma autorizacao fiscal",
                },
                {
                    "label": "Comunicação com o servidor",
                    "state": "ok" if online else "fail",
                    "detail": f"{len(online)} de {len(machines)} computadores",
                },
            ]
            for incident in (payload.get("incidents") or [])[:6]:
                result["occurrences"].append(
                    {
                        "title": str(incident.get("type") or "").upper(),
                        "started_at": incident.get("started_at"),
                        "recovered_at": incident.get("recovered_at"),
                        "duration": incident.get("observed_duration_seconds")
                        or incident.get("duration_seconds"),
                        "machines": ", ".join(incident.get("affected_machines") or []),
                    }
                )
        else:
            payload = _http_get(api_url + "/health", ca_file)
            monitors = payload.get("monitors") or {}
            result["store"] = payload.get("machine_name") or result["store"]
            has_connection = (state_dir() / "connection.json").is_file()
            result["needs_connection"] = not has_connection
            result["items"] = [
                {
                    "label": "Internet",
                    "state": _state((monitors.get("internet") or {}).get("ok")),
                    "detail": _latency(monitors.get("internet")),
                },
                {
                    "label": "Acesso à SEFAZ",
                    "state": _state((monitors.get("sefaz_tcp") or {}).get("ok")),
                    "detail": _latency(monitors.get("sefaz_tcp")),
                },
                {
                    "label": "Comunicação com o servidor",
                    "state": _state((monitors.get("server") or {}).get("ok"))
                    if has_connection
                    else "unknown",
                    "detail": _latency(monitors.get("server"))
                    if has_connection
                    else "Nenhuma conexão importada. Use Importar conexão.",
                },
            ]
            result["items"].append(
                {
                    "label": "Rede local",
                    "state": _state((monitors.get("gateway") or {}).get("ok")),
                    "detail": _latency(monitors.get("gateway")),
                }
            )
            # O pedido exige mostrar a ultima verificacao na janela.
            verificacoes = [
                str(monitor.get("checked_at"))
                for monitor in monitors.values()
                if isinstance(monitor, dict) and monitor.get("checked_at")
            ]
            # Sem checked_at, usa o horario em que o agente respondeu.
            result["last_check"] = (
                max(verificacoes) if verificacoes else payload.get("time_utc")
            )

            queue = payload.get("queue") or {}
            result["queue_pending"] = queue.get("total")
    except Exception as exc:  # noqa: BLE001 - a UI nunca deve quebrar
        result["error"] = f"{type(exc).__name__}: {exc}"

    return result


def _latency(monitor: dict[str, Any] | None) -> str:
    if not monitor:
        return "sem dados"
    latency = monitor.get("latency_ms")
    if latency is None:
        return "sem dados" if monitor.get("ok") is None else "respondendo"
    return f"{float(latency):.0f} ms"


class Api:
    """Ponte chamada pelo JavaScript da janela."""

    def __init__(self, role: dict[str, Any]) -> None:
        self.role = role
        self.window: Any = None

    def get_status(self) -> dict[str, Any]:
        data = collect_status(self.role)
        self.last_status = data
        return data

    def open_dashboard(self) -> dict[str, Any]:
        """Navega a janela para o painel da loja (nao apenas reexibe)."""
        url = panel_url(self.role)
        if not url:
            return {"ok": False, "detail": "O painel ainda nao esta disponivel para esta maquina."}
        if self.window is None:
            return {"ok": False, "detail": "Janela indisponivel."}
        try:
            self.window.load_url(url)
            return {"ok": True, "detail": "Painel aberto em " + url}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    def import_connection(self) -> dict[str, Any]:
        """Seleciona e importa o arquivo .hubconn da loja."""
        if self.window is None or webview is None:
            return {"ok": False, "detail": "Janela indisponivel."}
        try:
            selected = self.window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Arquivo de conexao (*.hubconn;*.json)", "Todos os arquivos (*.*)"),
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": f"Falha ao abrir o seletor: {exc}"}
        if not selected:
            return {"ok": False, "detail": "Nenhum arquivo selecionado."}

        source = Path(selected[0])
        try:
            read_connection(source, allow_http=False)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": str(exc)}

        if os.name != "nt" or not getattr(sys, "frozen", False):
            return {
                "ok": False,
                "detail": "A importacao so grava a conexao no produto instalado (Windows).",
            }
        return _install_connection_elevated(source)

    def close_window(self) -> bool:
        if self.window is not None:
            self.window.hide()
        return True

    def quit_app(self) -> bool:
        if self.window is not None:
            self.window.destroy()
        return True


def tray_summary(status: dict[str, Any]) -> str:
    """Resumo curto exibido no menu da bandeja."""
    itens = (status or {}).get("items") or []
    if not itens:
        return "Estado: ainda sem dados"
    rotulos = {"ok": "normal", "fail": "falha", "unknown": "sem dados"}
    partes = []
    for item in itens[:3]:
        estado = rotulos.get(str(item.get("state")), "sem dados")
        partes.append(str(item.get("label")) + ": " + estado)
    return " | ".join(partes)


def _build_icon():
    if Image is None or not ICON_FILE.is_file():
        return None
    return Image.open(ICON_FILE)


def _tray_thread(api: Api, role: dict[str, Any]) -> threading.Thread | None:
    if pystray is None:
        return None
    image = _build_icon()
    if image is None:
        return None

    def on_open(icon=None, item=None):
        if api.window is not None:
            api.window.show()

    def on_import(icon=None, item=None):
        # O seletor de arquivo precisa da janela como dona.
        if api.window is not None:
            api.window.show()
        try:
            api.import_connection()
        except Exception:  # noqa: BLE001 - a bandeja nunca deve quebrar
            pass

    def on_quit(icon=None, item=None):
        if api.window is not None:
            api.window.destroy()
        icon.stop()

    def resumo():
        return tray_summary(getattr(api, "last_status", {}))

    # Item 1: estado resumido (sem acao). Texto pode ser callable; se a
    # versao do pystray nao aceitar, cai para texto estatico.
    try:
        item_estado = pystray.MenuItem(lambda item=None: resumo(), None)
    except TypeError:
        item_estado = pystray.MenuItem(resumo(), None)

    menu = pystray.Menu(
        item_estado,
        pystray.MenuItem("Abrir a janela", on_open, default=True),
        pystray.MenuItem("Importar conexão…", on_import),
        pystray.MenuItem("Sair da bandeja (coleta continua)", on_quit),
    )
    icon = pystray.Icon("HUBMonitor", image, "HUB Monitoramento", menu)
    thread = threading.Thread(target=icon.run, name="tray", daemon=True)
    thread.start()
    return thread


def ps_quote(value: str) -> str:
    """Literais do PowerShell em aspas simples: ' vira ''.

    Sem isso, um .hubconn salvo em pasta com apostrofo (ex.: "Joao's")
    quebraria o comando e a elevacao falharia.
    """
    return "'" + str(value).replace("'", "''") + "'"


def elevation_command(executable: str, source: Path) -> str:
    return (
        "Start-Process -FilePath " + ps_quote(executable)
        + " -ArgumentList 'ui','--import-connection'," + ps_quote(str(source))
        + " -Verb RunAs -Wait -PassThru | Select-Object -ExpandProperty ExitCode"
    )


def _install_connection_elevated(source: Path) -> dict[str, Any]:
    """Importa a conexao com elevacao (a pasta de dados e restrita)."""
    command = elevation_command(sys.executable, source)
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "detail": f"Falha ao elevar: {exc}"}

    lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    exit_code = lines[-1] if lines else ""
    if exit_code == "0":
        return {"ok": True, "detail": "Conexao importada e agente respondendo."}
    if exit_code == "4":
        return {
            "ok": True,
            "detail": (
                "Conexao gravada, mas o agente ainda nao respondeu. "
                "Verifique o servico HUBMonitorAgent e clique em Atualizar."
            ),
        }
    detail = (completed.stderr or "").strip() or "Importacao cancelada ou recusada."
    return {"ok": False, "detail": detail[:300]}


def _restart_agent_service() -> None:
    if os.name != "nt":
        return
    for action in ("stop", "start"):
        try:
            subprocess.run(
                ["sc.exe", action, "HUBMonitorAgent"], capture_output=True, timeout=30
            )
        except (OSError, subprocess.SubprocessError):
            pass
        time.sleep(2)


def _wait_agent_health(timeout: float = 25.0) -> bool:
    """Confirma que o agente voltou a responder apos o reinicio.

    Sem isso o produto afirma "conexao importada" mesmo que o servico
    nao tenha subido - e o operador acredita que esta tudo certo.
    """
    if httpx is None:
        return True  # sem cliente HTTP nao ha como verificar
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            payload = _http_get("http://127.0.0.1:8010/health", None)
            if isinstance(payload, dict) and payload.get("status") == "ok":
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2.0)
    return False


def import_connection_cli(source: str) -> int:
    """Executado elevado: valida, grava em ProgramData e reinicia o agente."""
    path = Path(source)
    try:
        data = read_connection(path, allow_http=False)
    except Exception as exc:  # noqa: BLE001
        print(f"Arquivo de conexao invalido: {exc}", file=sys.stderr)
        return 2

    target = state_dir() / "connection.json"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        write_connection(target, data)
    except Exception as exc:  # noqa: BLE001
        print(f"Falha ao gravar a conexao: {exc}", file=sys.stderr)
        return 3

    _restart_agent_service()

    online = _wait_agent_health()
    print(
        json.dumps(
            {
                "ok": True,
                "path": str(target),
                "store": data.get("store_name"),
                "agent_online": online,
            },
            ensure_ascii=False,
        )
    )
    # 4 = gravado, mas o agente nao confirmou: a janela avisa o operador.
    return 0 if online else 4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="HUBMonitor", description="HUB Monitoramento")
    parser.add_argument("--tray-only", action="store_true")
    parser.add_argument("--print-status", action="store_true")
    parser.add_argument("--import-connection", metavar="ARQUIVO", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.import_connection:
        return import_connection_cli(args.import_connection)

    role = load_role()

    if args.print_status:
        print(json.dumps(collect_status(role), ensure_ascii=False, indent=2))
        return 0

    if webview is None:
        print(
            "pywebview nao esta instalado. Instale com: pip install pywebview pystray pillow",
            file=sys.stderr,
        )
        return 2

    api = Api(role)
    # Conteudo embutido em vez de file://: o WebView2 aplica restricoes ao
    # esquema file que podem impedir a injecao da API do pywebview.
    page = (
        UI_FILE.read_text(encoding="utf-8")
        if UI_FILE.is_file()
        else "<h1>Interface não encontrada.</h1>"
    )
    window = webview.create_window(
        "HUB Monitoramento",
        html=page,
        js_api=api,
        width=980,
        height=720,
        min_size=(760, 560),
    )
    api.window = window

    def on_closing():
        window.hide()
        return False  # fecha a janela, mantem a coleta

    try:
        window.events.closing += on_closing
    except Exception:  # noqa: BLE001
        pass

    _tray_thread(api, role)
    webview.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
