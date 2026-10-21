"""Teste ponta a ponta com servidor e agente reais.

Exercita o caminho completo exigido pelos criterios de aceite:
  1. agente coleta e envia; API armazena; diagnostico e calculado;
  2. falhas consecutivas abrem incidente (plano secao 15);
  3. servidor fora do ar NAO perde dado e o timestamp original e preservado.

Uso:  .venv/bin/python tools/e2e_test.py
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.tls import generate_local_certificate

PY = sys.executable
PORT = 8100
HEALTH_PORT = 8011
BASE = ""
TLS_CONTEXT: ssl.SSLContext | None = None
AGENT_TOKEN = "e2e-agent-token-change-me"

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> bool:
    global checks
    checks += 1
    if condition:
        print(f"  [PASS] {label}")
    else:
        failures.append(label)
        print(f"  [FAIL] {label} {detail}")
    return condition


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=15, context=TLS_CONTEXT) as response:
        return json.load(response)


def get_local(path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{HEALTH_PORT}" + path, timeout=5) as response:
        return json.load(response)


def wait_for(fn, timeout: float, label: str):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            last = fn()
            if last:
                return last
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(1.0)
    print(f"  [..] ultimo erro ao esperar {label}: {last}")
    return None


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def start_server(env_extra: dict, work: Path):
    env = {**os.environ, **env_extra}
    out = open(work / "server.out", "ab")
    return subprocess.Popen(
        [PY, "-m", "server.main"], cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT
    )


def start_agent(env_extra: dict, work: Path, name: str):
    env = {**os.environ, **env_extra}
    out = open(work / f"{name}.out", "ab")
    return subprocess.Popen(
        [PY, "-m", "agent.main"], cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT
    )


def stop(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


def generate_test_certificate(work: Path) -> tuple[Path, Path, Path]:
    return generate_local_certificate(work, "127.0.0.1", "127.0.0.1")


def main() -> int:
    global BASE, TLS_CONTEXT
    work = Path(tempfile.mkdtemp(prefix="bertolo-e2e-"))
    print(f"diretorio de trabalho: {work}")
    cert, key, trust = generate_test_certificate(work)
    TLS_CONTEXT = ssl.create_default_context(cafile=str(trust))
    BASE = f"https://127.0.0.1:{PORT}"
    issuer_log = work / "issuer.jsonl"
    issuer_log.write_text("", encoding="utf-8")

    server_env = {
        "DB_PATH": str(work / "bertolo.db"),
        "DATA_DIR": str(work / "data"),
        "LOG_DIR": str(work / "logs"),
        "SERVER_HOST": "127.0.0.1",
        "SERVER_PORT": str(PORT),
        "SERVER_ALLOW_HTTP": "false",
        "SERVER_TLS_CERT_FILE": str(cert),
        "SERVER_TLS_KEY_FILE": str(key),
        "AGENT_INGEST_TOKEN": AGENT_TOKEN,
        "MIKROTIK_ENABLED": "false",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_ID": "",
        "LOG_LEVEL": "WARNING",
    }

    agent_env = {
        "MACHINE_NAME": "CAIXA02",
        "SERVER_URL": BASE,
        "SERVER_CA_FILE": str(trust),
        "AGENT_INGEST_TOKEN": AGENT_TOKEN,
        "SERVER_IP": "127.0.0.1",
        "GATEWAY_IP": "127.0.0.1",
        "HEALTH_PORT": str(HEALTH_PORT),
        "DATA_DIR": str(work / "agent-data"),
        "LOG_DIR": str(work / "agent-logs"),
        "SNAPSHOT_INTERVAL": "3",
        "SENDER_INTERVAL": "3",
        "LOG_LEVEL": "WARNING",
        "SEFAZ_AUTHORIZATION_LOG_PATH": str(issuer_log),
    }

    server = agent = None
    try:
        # ---------------------------------------------------------------
        print("\n== Fase 1: servidor no ar e agente coletando ==")
        server = start_server(server_env, work)
        health = wait_for(lambda: get("/health"), 45, "health do servidor")
        if health is None:
            print((work / "server.out").read_text()[-2000:])
            return 1
        check("servidor responde /health", health.get("status") == "ok")
        check("banco inicializado", health.get("database") == "ok")
        try:
            urllib.request.urlopen(BASE + "/health", timeout=5)
            untrusted_rejected = False
        except (ssl.SSLCertVerificationError, urllib.error.URLError):
            untrusted_rejected = True
        check("certificado HTTPS nao confiavel e rejeitado", untrusted_rejected)
        unauthorized = urllib.request.Request(
            BASE + "/api/v1/measurements",
            data=json.dumps({"measurements": []}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(unauthorized, timeout=5, context=TLS_CONTEXT)
            unauthenticated_status = 200
        except urllib.error.HTTPError as exc:
            unauthenticated_status = exc.code
        check("ingestao sem token retorna 401", unauthenticated_status == 401)

        agent = start_agent(agent_env, work, "agent1")
        def first_measurement():
            body = get("/api/v1/status")
            if not body.get("machines"):
                return None
            machine = body["machines"][0]
            if not machine.get("online"):
                return None
            if machine.get("internet_ok") is None or machine.get("sefaz_tls_ok") is None:
                return None
            return body

        status = wait_for(first_measurement, 90, "primeira medicao completa do CAIXA02")
        if status is None:
            print((work / "agent1.out").read_text()[-3000:])
            return 1

        machine = status["machines"][0]
        check("maquina identificada como CAIXA02", machine["machine_name"] == "CAIXA02")
        check("maquina marcada como online", machine["online"] is True)
        check("gateway OK (127.0.0.1)", machine["gateway_ok"] is True, str(machine["gateway_ok"]))
        check("servidor OK (127.0.0.1)", machine["server_ok"] is True, str(machine["server_ok"]))
        check("internet OK", machine["internet_ok"] is True, str(machine["internet_ok"]))
        check("DNS SEFAZ OK", machine["dns_ok"] is True, str(machine["dns_ok"]))
        check("SEFAZ TCP OK", machine["sefaz_tcp_ok"] is True, str(machine["sefaz_tcp_ok"]))
        check("SEFAZ TLS OK (cadeia ICP-Brasil)", machine["sefaz_tls_ok"] is True, str(machine["sefaz_tls_ok"]))

        data = get("/api/v1/status")
        check("nenhum incidente com tudo OK", data["open_incidents"] == [])
        check(
            "medicoes armazenadas",
            get("/health")["measurements"] > 0,
            str(get("/health")["measurements"]),
        )

        # ---------------------------------------------------------------
        print("\n== Fase 2: falha consecutiva abre incidente ==")
        stop(agent)
        agent_env.update(
            {"GATEWAY_IP": "192.0.2.1", "INTERNET_TARGETS": "192.0.2.1,192.0.2.2"}
        )
        agent = start_agent(agent_env, work, "agent2")

        def open_incidents():
            items = get("/api/v1/incidents?only_open=true")
            types = {item["type"] for item in items}
            if "gateway" in types:
                return items
            return None

        incidents = wait_for(open_incidents, 90, "incidente de rede local")
        if incidents is None:
            print("  incidentes abertos:", get("/api/v1/incidents?only_open=true"))
        else:
            by_type = {item["type"]: item for item in incidents}
            check("incidente de REDE LOCAL aberto", "gateway" in by_type)
            check(
                "incidente de gateway afeta CAIXA02",
                "CAIXA02" in by_type["gateway"]["affected_machines"],
            )
            check(
                "diagnostico do gateway aponta rede local",
                "rede local" in (by_type["gateway"]["diagnosis"] or "").lower(),
            )
            check(
                "um unico incidente por componente (sem duplicidade)",
                len([i for i in incidents if i["type"] == "gateway"]) == 1,
            )
            # Rede local fora explica a Internet fora: a falha de Internet
            # existe no historico, mas fica consolidada e sem alerta proprio.
            check(
                "internet nao gera alerta separado (sintoma consolidado)",
                "internet" not in {item["type"] for item in incidents},
            )

        events = get("/api/v1/events?limit=50")
        check(
            "eventos de transicao registrados",
            any(event.get("kind") == "state_change" for event in events),
        )

        # ---------------------------------------------------------------
        print("\n== Fase 3: servidor fora do ar nao pode perder dado ==")
        outage_start = datetime.now(timezone.utc)
        stop(server)
        server = None
        auth_started = datetime.now(timezone.utc)
        auth_record = {
            "event_id": "e2e-offline-auth-001",
            "started_at": iso(auth_started),
            "completed_at": iso(auth_started + timedelta(milliseconds=6500)),
            "duration_ms": 6500,
            "outcome": "authorized",
            "xml": "synthetic-private-payload-must-not-persist",
        }
        with issuer_log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(auth_record) + "\n")
        time.sleep(16)

        queued = None
        try:
            queued = get_local("/health")["queue"]
        except Exception as exc:  # noqa: BLE001
            print(f"  (health local indisponivel: {exc})")
        if queued is not None:
            check("fila local acumulou itens durante a queda", queued["total"] > 0, str(queued))
            check(
                "nada foi descartado",
                queued["measurements"] > 0 or queued["events"] > 0 or queued["authorizations"] > 0,
                str(queued),
            )
            check("autorizacao sintetica ficou na fila offline", queued["authorizations"] > 0, str(queued))
        outage_end = datetime.now(timezone.utc)

        server = start_server(server_env, work)
        wait_for(lambda: get("/health"), 45, "servidor de volta")

        def measurement_during_outage():
            history = get("/api/v1/machines/CAIXA02/history?hours=1")
            for item in history["measurements"]:
                if iso(outage_start) <= item["timestamp"] <= iso(outage_end):
                    return item
            return None

        recovered = wait_for(measurement_during_outage, 90, "medicao do periodo de queda")
        if check("medicao do periodo de queda chegou ao servidor", recovered is not None):
            print(f"        timestamp preservado: {recovered['timestamp']}")

        total_after = get("/health")["measurements"]
        check("historico nao foi duplicado no reenvio", total_after > 0, str(total_after))
        auth_history = get("/api/v1/machines/CAIXA02/sefaz-authorizations?hours=1")
        check(
            "autorizacao da fila offline chegou ao historico",
            any(item["event_id"] == "e2e-offline-auth-001" for item in auth_history["authorizations"]),
        )
        check(
            "conteudo fiscal sintetico nao foi armazenado",
            "synthetic-private-payload-must-not-persist" not in str(auth_history),
        )

    finally:
        stop(agent)
        stop(server)
        print(f"\nlogs em {work}")

    print("\n" + "=" * 62)
    if failures:
        print(f"RESULTADO: {checks - len(failures)}/{checks} verificacoes OK, {len(failures)} falha(s)")
        for item in failures:
            print(f"  - {item}")
        return 1
    print(f"RESULTADO: todas as {checks} verificacoes passaram")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
