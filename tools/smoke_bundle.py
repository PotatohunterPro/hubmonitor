"""Valida um bundle do HUBMonitor gerado pelo PyInstaller.

Funciona no macOS e no Windows. Verifica o conteudo do bundle e executa
o proprio executavel: comando version, servidor em HTTP local, /health e
a pagina do painel.

Uso:
    python tools/smoke_bundle.py /caminho/dist/HUBMonitor
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

failures: list[str] = []
checks = 0


def check(label: str, ok: bool, detail: str = "") -> bool:
    global checks
    checks += 1
    if ok:
        print(f"  [PASS] {label}")
    else:
        failures.append(label)
        print(f"  [FAIL] {label} {detail}")
    return ok


def find_executable(bundle: Path) -> Path | None:
    for name in ("HUBMonitor.exe", "HUBMonitor"):
        candidate = bundle / name
        if candidate.is_file():
            return candidate
    return None


def data_root(bundle: Path) -> Path:
    internal = bundle / "_internal"
    return internal if internal.is_dir() else bundle


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_health(port: int, timeout: float) -> dict | None:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                return json.load(response)
        except Exception:  # noqa: BLE001
            time.sleep(1.0)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", help="pasta dist/HUBMonitor")
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()

    bundle = Path(args.bundle).resolve()
    print(f"bundle: {bundle}")

    if not bundle.is_dir():
        check("bundle existe", False, str(bundle))
        return 1

    executable = find_executable(bundle)
    if executable is None:
        check("executavel HUBMonitor presente", False, "nem .exe nem binario encontrado")
        return 1
    check("executavel HUBMonitor presente", True, executable.name)

    root = data_root(bundle)
    required = [
        root / "server" / "dashboard" / "templates" / "dashboard.html",
        root / "server" / "dashboard" / "static" / "vendor" / "chart.umd.min.js",
        root / "desktop" / "ui" / "index.html",
        root / "certs" / "icp-brasil-roots.pem",
    ]
    for path in required:
        check(f"recurso {path.name}", path.is_file(), str(path))

    print("\n== executando o binario congelado ==")
    try:
        version = subprocess.run(
            [str(executable), "version"], capture_output=True, text=True, timeout=120
        )
        check("comando version responde", version.returncode == 0, version.stderr[-200:])
    except (OSError, subprocess.SubprocessError) as exc:
        check("comando version responde", False, str(exc))

    port = free_port()
    work = Path(tempfile.mkdtemp(prefix="hubmonitor-bundle-"))
    env = {
        **os.environ,
        "SERVER_HOST": "127.0.0.1",
        "SERVER_PORT": str(port),
        "SERVER_ALLOW_HTTP": "true",
        "AGENT_INGEST_TOKEN": "credencial-de-teste-1234567890",
        "DB_PATH": str(work / "data" / "bertolo.db"),
        "DATA_DIR": str(work / "data"),
        "LOG_DIR": str(work / "logs"),
        "MIKROTIK_ENABLED": "false",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_ID": "",
        "LOG_LEVEL": "WARNING",
    }
    process = subprocess.Popen(
        [str(executable), "server"],
        env=env,
        cwd=str(work),
        stdout=(work / "server.out").open("ab"),
        stderr=subprocess.STDOUT,
    )
    try:
        health = wait_health(port, args.timeout)
        if health is None:
            print((work / "server.out").read_text(errors="replace")[-2000:])
            check("servidor congelado responde em /health", False, "timeout")
        else:
            check("servidor congelado responde em /health", health.get("status") == "ok")
            check("banco inicializado", health.get("database") == "ok")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
                    page = response.read().decode("utf-8", errors="replace")
                # Marcador estavel: nao depende do titulo configuravel.
                renderizado = page.lstrip().lower().startswith("<!doctype html") and "</html>" in page.lower()
                check("painel renderiza", renderizado, page[:80])
            except Exception as exc:  # noqa: BLE001
                check("painel renderiza", False, str(exc))
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()

    print("\n" + "=" * 60)
    if failures:
        print(f"RESULTADO: {checks - len(failures)}/{checks} OK, {len(failures)} falha(s)")
        for item in failures:
            print(f"  - {item}")
        return 1
    print(f"RESULTADO: todas as {checks} verificacoes passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
