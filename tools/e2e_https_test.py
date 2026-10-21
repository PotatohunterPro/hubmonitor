"""Teste ponta a ponta do caminho seguro: HTTPS + credencial do agente.

Prova, no macOS, o que o instalador promete no Windows:

  1. o servidor gera CA + certificado proprios;
  2. sobe em HTTPS;
  3. o arquivo .hubconn carrega a CA e a credencial;
  4. o agente usa esse arquivo e envia dados por HTTPS validado;
  5. credencial errada e recusada com 401;
  6. certificado errado e recusado pelo agente.

Uso: .venv/bin/python tools/e2e_https_test.py
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # O script roda de tools/, mas importa shared/agent/server.
    sys.path.insert(0, str(ROOT))
PY = sys.executable
from agent.config import detect_local_ip  # noqa: E402

#: IP da rede local: e por ele que os caixas chegam ao servidor.
LAN_IP = detect_local_ip("1.1.1.1")
PORT = 8443
HEALTH_PORT = 8012
CA_URL = f"https://127.0.0.1:{PORT}"

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


def stop(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    global PORT, HEALTH_PORT, CA_URL
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", help="bundle HUBMonitor; sem isso usa python -m")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--health-port", type=int, default=HEALTH_PORT)
    args = parser.parse_args()

    PORT = args.port
    HEALTH_PORT = args.health_port
    CA_URL = f"https://127.0.0.1:{PORT}"

    if args.exe:
        exe = str(Path(args.exe).resolve())
        server_cmd = [exe, "server"]
        agent_cmd = [exe, "agent"]
        print(f"usando bundle congelado: {exe}")
    else:
        server_cmd = [PY, "-m", "server.main"]
        agent_cmd = [PY, "-m", "agent.main"]
        print("usando codigo-fonte")

    work = Path(tempfile.mkdtemp(prefix="hubmonitor-https-"))
    cert_dir = work / "certs"
    print(f"diretorio de trabalho: {work}")

    server = agent = None
    try:
        print("\n== 1. Gerando CA e certificado do servidor ==")
        generated = subprocess.run(
            server_cmd + [
                "--generate-tls-cert",
                "--tls-dir", str(cert_dir),
                # Como o instalador faz: nome da maquina + IP da rede.
                # O loopback entra nos SANs automaticamente.
                "--server-name", "SERVIDOR-TESTE",
                "--server-ip", LAN_IP,
            ],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        if generated.returncode != 0:
            print(generated.stdout[-2000:])
            print(generated.stderr[-2000:])
            return 1
        cert = cert_dir / "server.pem"
        key = cert_dir / "server-key.pem"
        ca = cert_dir / "server-ca.pem"
        check("certificado gerado", cert.is_file() and key.is_file())
        check("CA publica gerada", ca.is_file())
        check(
            "chave privada nao esta na CA",
            "PRIVATE KEY" not in ca.read_text(encoding="utf-8"),
        )

        print("\n== 2. Subindo o servidor em HTTPS ==")
        server_env = {
            **os.environ,
            "SERVER_HOST": "0.0.0.0",
            "SERVER_PORT": str(PORT),
            "SERVER_TLS_CERT_FILE": str(cert),
            "SERVER_TLS_KEY_FILE": str(key),
            "AGENT_INGEST_TOKEN": "credencial-da-loja-1234567890",
            "DB_PATH": str(work / "data" / "bertolo.db"),
            "DATA_DIR": str(work / "data"),
            "LOG_DIR": str(work / "logs"),
            "MIKROTIK_ENABLED": "false",
            "TELEGRAM_BOT_TOKEN": "",
            "TELEGRAM_CHAT_ID": "",
            "LOG_LEVEL": "WARNING",
        }
        server = subprocess.Popen(
            server_cmd, cwd=ROOT, env=server_env,
            stdout=(work / "server.out").open("ab"), stderr=subprocess.STDOUT,
        )

        def https_health():
            response = httpx.get(CA_URL + "/health", verify=str(ca), timeout=5.0)
            response.raise_for_status()
            return response.json()

        health = wait_for(https_health, 60, "health HTTPS")
        if health is None:
            print((work / "server.out").read_text()[-2500:])
            return 1
        check("servidor responde em HTTPS com a CA da loja", health.get("status") == "ok")

        # O caixa chega pelo IP da rede, nao pelo loopback.
        if LAN_IP != "127.0.0.1":
            try:
                rede = httpx.get(f"https://{LAN_IP}:{PORT}/health", verify=str(ca), timeout=5.0)
                check("servidor responde no IP da rede com a CA da loja", rede.status_code == 200)
            except Exception as exc:  # noqa: BLE001
                check("servidor responde no IP da rede com a CA da loja", False, str(exc))

        unaverified = None
        try:
            httpx.get(CA_URL + "/health", timeout=5.0)
        except Exception as exc:  # noqa: BLE001
            unaverified = type(exc).__name__
        check("sem a CA o certificado e recusado", unaverified is not None, str(unaverified))

        print("\n== 3. Credencial do agente ==")
        payload = {
            "machine": {"machine_name": "CAIXA-AUTH", "hostname": "CAIXA-AUTH"},
            "measurements": [{"machine_name": "CAIXA-AUTH", "internet_ok": True}],
        }
        sem_token = httpx.post(CA_URL + "/api/v1/measurements", json=payload, verify=str(ca), timeout=10)
        check("ingestao sem credencial devolve 401", sem_token.status_code == 401)

        token_errado = httpx.post(
            CA_URL + "/api/v1/measurements",
            json=payload,
            headers={"Authorization": "Bearer credencial-errada"},
            verify=str(ca),
            timeout=10,
        )
        check("credencial errada devolve 401", token_errado.status_code == 401)

        correto = httpx.post(
            CA_URL + "/api/v1/measurements",
            json=payload,
            headers={"Authorization": "Bearer credencial-da-loja-1234567890"},
            verify=str(ca),
            timeout=10,
        )
        check("credencial correta aceita", correto.status_code == 200, correto.text[:200])

        print("\n== 4. Agente usando o arquivo .hubconn ==")
        from shared.connection_file import build_connection, write_connection

        connection = build_connection(
            store_name="Mercado Bertolo",
            base_url=CA_URL,
            agent_token="credencial-da-loja-1234567890",
            ca_certificate_pem=ca.read_text(encoding="utf-8"),
            server_name="SERVIDOR",
            fiscal={
                "uf": "SP",
                "document": "nfce",
                "host": "nfce.fazenda.sp.gov.br",
                "port": 443,
                "confirmed": True,
            },
        )
        connection_path = work / "loja.hubconn"
        write_connection(connection_path, connection)

        agent_env = {
            **os.environ,
            "CONNECTION_FILE": str(connection_path),
            "MACHINE_NAME": "CAIXA-E2E",
            "SERVER_IP": "127.0.0.1",
            "GATEWAY_IP": "127.0.0.1",
            "HEALTH_PORT": str(HEALTH_PORT),
            "DATA_DIR": str(work / "agent-data"),
            "LOG_DIR": str(work / "agent-logs"),
            "SNAPSHOT_INTERVAL": "2",
            "SENDER_INTERVAL": "2",
            "LOG_LEVEL": "WARNING",
        }
        agent = subprocess.Popen(
            agent_cmd, cwd=ROOT, env=agent_env,
            stdout=(work / "agent.out").open("ab"), stderr=subprocess.STDOUT,
        )

        def agent_health():
            try:
                response = httpx.get(f"http://127.0.0.1:{HEALTH_PORT}/health", timeout=3.0)
                response.raise_for_status()
                return response.json()
            except Exception:  # noqa: BLE001
                return None

        local_health = wait_for(agent_health, 45, "health local do agente")
        if local_health is None:
            print((work / "agent.out").read_text()[-2500:])
        else:
            check("agente respondeu no health local", local_health.get("status") == "ok")

        def connected():
            body = httpx.get(CA_URL + "/api/v1/status", verify=str(ca), timeout=8.0).json()
            for machine in body.get("machines", []):
                if machine.get("machine_name") == "CAIXA-E2E" and machine.get("online"):
                    return machine
            return None

        machine = wait_for(connected, 90, "CAIXA-E2E online no servidor")
        if machine is None:
            print((work / "agent.out").read_text()[-2500:])
        else:
            check("agente enviou dados por HTTPS validado", True)
            check(
                "destino fiscal do .hubconn chegou ao agente",
                machine.get("sefaz_tcp_ok") in (True, False),
                str(machine.get("sefaz_tcp_ok")),
            )

        def drained():
            body = agent_health()
            if not body:
                return None
            sender = body.get("sender") or {}
            queue = body.get("queue") or {}
            if sender.get("last_success_at") is None:
                return None
            if int(queue.get("total") or 0) != 0:
                return None
            return queue

        queue = wait_for(drained, 30, "fila local drenar")
        check("fila local esvaziou apos envio", queue is not None, str(queue))

        print("\n== 5. Certificado errado no agente ==")
        outro_dir = work / "outra-ca"
        subprocess.run(
            server_cmd + [
                "--generate-tls-cert",
                "--tls-dir", str(outro_dir),
                "--server-name", "127.0.0.1", "--server-ip", "127.0.0.1",
            ],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        import ssl

        from agent.tlsutil import build_ssl_context

        context = build_ssl_context(verify=True)
        try:
            context.load_verify_locations(cafile=str(outro_dir / "server-ca.pem"))
        except ssl.SSLError:
            pass
        rejeitado = False
        try:
            httpx.get(CA_URL + "/health", verify=str(outro_dir / "server-ca.pem"), timeout=5.0)
        except Exception:  # noqa: BLE001
            rejeitado = True
        check("CA de outra loja nao valida este servidor", rejeitado)

    finally:
        stop(agent)
        stop(server)
        print(f"\nlogs em {work}")

    print("\n" + "=" * 62)
    if failures:
        print(f"RESULTADO: {checks - len(failures)}/{checks} OK, {len(failures)} falha(s)")
        for item in failures:
            print(f"  - {item}")
        return 1
    print(f"RESULTADO: todas as {checks} verificacoes passaram")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
