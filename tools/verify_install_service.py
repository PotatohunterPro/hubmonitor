"""Executa o bootstrap do servico (install-service.ps1) com stubs.

O script e o mais complexo do instalador e nunca foi executado. Aqui ele
roda de verdade no macOS/PowerShell 7, com as APIs do Windows
substituidas por stubs, contra uma pasta temporaria. Verifica o que o
instalador produz: .env, credencial, certificados, role.json, porta e
idempotencia.

Uso: .venv/bin/python tools/verify_install_service.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
failures: list[str] = []
checks = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if ok:
        print(f"  [PASS] {label}")
    else:
        failures.append(label)
        print(f"  [FAIL] {label} {detail}")


def pwsh() -> str:
    for candidate in (shutil.which("pwsh"), str(ROOT / ".pwsh" / "pwsh")):
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit("PowerShell 7 nao encontrado")


FAKE_EXE = """#!/bin/sh
if [ -n "$HUB_EXE_MARKER" ]; then
  echo "exe $*" >> "$HUB_EXE_MARKER"
fi
dir=""
path=""
while [ $# -gt 0 ]; do
  case "$1" in
    --tls-dir) dir="$2"; shift 2 ;;
    --path) path="$2"; shift 2 ;;
    *) shift ;;
  esac
done
if [ -n "$path" ]; then
  printf '%s\n' '{"version":1,"kind":"hubmonitor-store-connection","fingerprint":"00"}' > "$path"
fi
if [ -n "$dir" ]; then
  mkdir -p "$dir"
  printf '%s\n' "-----BEGIN CERTIFICATE-----" "FAKE-SERVER" "-----END CERTIFICATE-----" > "$dir/server.pem"
  printf '%s\n' "-----BEGIN PRIVATE KEY-----" "FAKE-KEY" "-----END PRIVATE KEY-----" > "$dir/server-key.pem"
  printf '%s\n' "-----BEGIN CERTIFICATE-----" "FAKE-CA" "-----END CERTIFICATE-----" > "$dir/server-ca.pem"
fi
exit 0
"""

STUB = "#!/bin/sh\nexit 0\n"

# O wrapper do servico e copiado do winsw.exe; este stub registra qual
# servico foi instalado, permitindo verificar os dois papeis.
WINSW_STUB = """#!/bin/sh
exit 0
"""

# No macOS o Copy-Item perde o bit de execucao do wrapper .exe, entao o
# stub do winsw nao roda. O sc.exe (no PATH) roda de verdade e e chamado
# logo depois de cada registracao: e por ele que observamos o servico.
# Registra cada caminho cuja ACL foi restringida.
ACL_STUB = """#!/bin/sh
if [ -n "$HUB_ACL_MARKER" ]; then
  echo "icacls $*" >> "$HUB_ACL_MARKER"
fi
exit 0
"""

SC_STUB = """#!/bin/sh
if [ -n "$HUB_SERVICE_MARKER" ]; then
  echo "sc.exe $*" >> "$HUB_SERVICE_MARKER"
fi
exit 0
"""

WRAPPER = r'''
[CmdletBinding()]
param(
    [string]$InstallDir,
    [int]$Port,
    [string]$StoreName,
    [string]$MachineName,
    [string]$Mode = 'server',
    [string]$Action = 'install',
    [string]$LanIp = '',
    [string]$LocalSubnet = '192.168.0.0/24'
)

function Get-Service {
    [CmdletBinding()] param([string]$Name)
    return $null
}
function Stop-Service { [CmdletBinding()] param([string]$Name, [switch]$Force) }
function Restart-Service { [CmdletBinding()] param([string]$Name, [switch]$Force) }
function Get-NetFirewallRule {
    [CmdletBinding()] param([string]$DisplayName)
    return $null
}
function Remove-NetFirewallRule { [CmdletBinding()] param([Parameter(ValueFromPipeline = $true)]$InputObject) }
function New-NetFirewallRule {
    [CmdletBinding()]
    param(
        [string]$DisplayName,
        [string]$Direction,
        [string]$Action,
        [string]$Protocol,
        [int]$LocalPort,
        [string]$RemoteAddress,
        [string]$Profile
    )
    return $null
}
function Import-Certificate {
    [CmdletBinding()] param([string]$FilePath, [string]$CertStoreLocation)
    return $null
}
function Invoke-RestMethod {
    [CmdletBinding()]
    param([string]$Uri, [int]$TimeoutSec = 5)
    return [pscustomobject]@{ status = 'ok'; version = 'teste'; database = 'ok' }
}
function New-ScheduledTaskAction {
    [CmdletBinding()] param([string]$Execute, [string]$Argument, [string]$WorkingDirectory)
    return [pscustomobject]@{ Execute = $Execute; Argument = $Argument }
}
function New-ScheduledTaskTrigger { [CmdletBinding()] param([switch]$Daily, [string]$At) return $null }
function New-ScheduledTaskPrincipal { [CmdletBinding()] param([string]$UserId, [string]$LogonType, [string]$RunLevel) return $null }
function New-ScheduledTaskSettingsSet { [CmdletBinding()] param([switch]$StartWhenAvailable, $ExecutionTimeLimit) return $null }
function Register-ScheduledTask {
    [CmdletBinding()]
    param([string]$TaskName, $Action, $Trigger, $Principal, $Settings, [switch]$Force)
    if ($env:HUB_TASK_MARKER) {
        Add-Content -LiteralPath $env:HUB_TASK_MARKER -Value ('REGISTER|' + $TaskName + '|' + $Action.Argument + '|' + $Action.Execute)
    }
    return $null
}
function Unregister-ScheduledTask {
    [CmdletBinding()] param([string]$TaskName, [switch]$Confirm)
    if ($env:HUB_TASK_MARKER) {
        Add-Content -LiteralPath $env:HUB_TASK_MARKER -Value ('UNREGISTER|' + $TaskName)
    }
}

# & (e nao dot-source): o exit do script precisa definir o codigo do
# processo, exatamente como o NSIS invoca com -File.
& '__SCRIPT__' -Mode $Mode -InstallDir $InstallDir -Port $Port -StoreName $StoreName -MachineName $MachineName -LocalSubnet $LocalSubnet -LanIp $LanIp -Action $Action
# O exit do script chamado nao encerra o processo; propaga o codigo.
exit $LASTEXITCODE
'''


def run_once(
    shell: str, wrapper: Path, install_dir: Path, port: int, env: dict,
    mode: str = "server", action: str = "install",
    lan_ip: str = "", subnet: str = "",
) -> subprocess.CompletedProcess:
    arguments = [
        shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wrapper),
        "-InstallDir", str(install_dir), "-Port", str(port),
        "-StoreName", "Mercado Bertolo", "-MachineName", "SERVIDOR-TESTE",
        "-Mode", mode, "-Action", action,
    ]
    if lan_ip:
        arguments += ["-LanIp", lan_ip]
    if subnet:
        arguments += ["-LocalSubnet", subnet]
    return subprocess.run(
        arguments,
        capture_output=True, text=True, timeout=180, env=env,
    )


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def main() -> int:
    shell = pwsh()
    work = Path(tempfile.mkdtemp(prefix="hubmonitor-install-"))
    install_dir = work / "Program Files" / "HUB Monitoramento"
    install_dir.mkdir(parents=True)
    program_data = work / "ProgramData"
    program_data.mkdir()
    stub_bin = work / "bin"
    stub_bin.mkdir()

    exe = install_dir / "HUBMonitor.exe"
    exe.write_text(FAKE_EXE, encoding="utf-8")
    exe.chmod(0o755)
    winsw = install_dir / "winsw.exe"
    winsw.write_text(WINSW_STUB, encoding="utf-8")
    winsw.chmod(0o755)
    for name, content in (("icacls", ACL_STUB), ("sc.exe", SC_STUB)):
        stub = stub_bin / name
        stub.write_text(content, encoding="utf-8")
        stub.chmod(0o755)

    # O wrapper faz dot-source do script; ele precisa estar ao lado.
    shutil.copy(ROOT / "packaging" / "install-service.ps1", work / "install-service.ps1")

    wrapper = work / "harness.ps1"
    wrapper.write_text(
        WRAPPER.replace("__SCRIPT__", str(work / "install-service.ps1")), encoding="utf-8"
    )

    env = {
        **os.environ,
        # macOS diferencia maiusculas em nomes de variavel; o script le
        # $env:ProgramData, entao as duas grafias sao definidas.
        "PROGRAMDATA": str(program_data),
        "ProgramData": str(program_data),
        "COMPUTERNAME": "SERVIDOR-TESTE",
        "HUB_TASK_MARKER": str(work / "tasks.txt"),
        "HUB_SERVICE_MARKER": str(work / "services-server.txt"),
        "HUB_EXE_MARKER": str(work / "exe-args.txt"),
        "HUB_ACL_MARKER": str(work / "acl.txt"),
        "PATH": str(stub_bin) + os.pathsep + os.environ.get("PATH", ""),
    }

    print(f"executando install-service.ps1 contra {install_dir}")
    first = run_once(
        shell, wrapper, install_dir, 8443, env,
        lan_ip="10.9.8.7", subnet="10.9.8.0/24",
    )
    check("primeira execucao termina com codigo 0", first.returncode == 0,
          (first.stdout[-600:] + first.stderr[-600:]))
    if first.returncode != 0:
        print(first.stdout[-1500:])
        print(first.stderr[-1500:])
        return 1

    env_file = install_dir / ".env"
    check(".env criado", env_file.is_file())
    if not env_file.is_file():
        return 1

    raw = env_file.read_bytes()
    check(".env sem BOM", not raw.startswith(b"\xef\xbb\xbf"))

    values = read_env(env_file)
    check("porta gravada", values.get("SERVER_PORT") == "8443", values.get("SERVER_PORT", ""))
    token = values.get("AGENT_INGEST_TOKEN", "")
    check("credencial gerada", len(token) >= 32, str(len(token)))
    check("HTTPS obrigatorio", values.get("SERVER_ALLOW_HTTP") == "false")
    certs = program_data / "HUBMonitor" / "certs"
    check("certificado do servidor criado", (certs / "server.pem").is_file())
    check("chave privada criada", (certs / "server-key.pem").is_file())
    check("CA publica criada", (certs / "server-ca.pem").is_file())
    check(
        "caminho do certificado no .env",
        values.get("SERVER_TLS_CERT_FILE", "").endswith("server.pem"),
        values.get("SERVER_TLS_CERT_FILE", ""),
    )
    check(
        "dados fora de Program Files",
        values.get("DATA_DIR", "").startswith(str(program_data)),
        values.get("DATA_DIR", ""),
    )
    check("nome da loja gravado", values.get("STORE_NAME") == "Mercado Bertolo")
    check(
        "rede local informada gravada no .env",
        values.get("LOCAL_SUBNET") == "10.9.8.0/24",
        values.get("LOCAL_SUBNET", ""),
    )
    argumentos = (work / "exe-args.txt").read_text(encoding="utf-8")
    check(
        "IP informado chega ao certificado",
        "--server-ip 10.9.8.7" in argumentos,
        argumentos,
    )
    role_file = program_data / "HUBMonitor" / "role.json"
    check("role.json criado", role_file.is_file())

    acls = (work / "acl.txt").read_text(encoding="utf-8") if (work / "acl.txt").is_file() else ""
    check("diretorio de dados restrito", "HUBMonitor/data" in acls.replace("\\", "/"), acls[:300])
    check("diretorio de logs restrito", "HUBMonitor/logs" in acls.replace("\\", "/"), acls[:300])
    check("chave privada restrita", "server-key.pem" in acls, acls[:300])

    servicos = (work / "services-server.txt").read_text(encoding="utf-8")
    check("servico do servidor registrado", "failure HUBMonitorServer" in servicos, servicos)
    check("agente da propria maquina registrado", "failure HUBMonitorAgent" in servicos, servicos)
    check(
        "conexao da propria maquina gerada",
        (program_data / "HUBMonitor" / "server-connection.json").is_file(),
    )

    marker = work / "tasks.txt"
    registros = marker.read_text(encoding="utf-8").splitlines() if marker.is_file() else []
    backup = [line for line in registros if line.startswith("REGISTER|HUBMonitorBackup|")]
    check("backup diario agendado", bool(backup), str(registros))
    if backup:
        check("backup usa o comando correto", backup[0].split("|")[2] == "server --backup", backup[0])

    before_cert = (certs / "server.pem").read_bytes()

    print("executando novamente (idempotencia)")
    second = run_once(shell, wrapper, install_dir, 8443, env)
    check("segunda execucao termina com codigo 0", second.returncode == 0,
          (second.stdout[-600:] + second.stderr[-600:]))

    values2 = read_env(env_file)
    check("credencial preservada", values2.get("AGENT_INGEST_TOKEN") == token)
    check("certificado preservado", (certs / "server.pem").read_bytes() == before_cert)
    check("porta preservada", values2.get("SERVER_PORT") == "8443")

    print("\n== desinstalar e reinstalar ==")
    token_antes = values.get("AGENT_INGEST_TOKEN", "")
    backup = program_data / "HUBMonitor" / "config-backup.env"
    backup.write_bytes(env_file.read_bytes())
    env_file.unlink()  # a desinstalacao remove a pasta do programa
    reinstalado = run_once(shell, wrapper, install_dir, 8443, env)
    check("reinstalacao termina com codigo 0", reinstalado.returncode == 0,
          (reinstalado.stdout[-400:] + reinstalado.stderr[-400:]))
    valores_apos = read_env(env_file) if env_file.is_file() else {}
    check(
        "credencial sobrevive a desinstalacao",
        valores_apos.get("AGENT_INGEST_TOKEN") == token_antes,
        valores_apos.get("AGENT_INGEST_TOKEN", "")[:12],
    )

    print("\n== modo agente ==")
    agent_dir = work / "Program Files" / "Agente"
    agent_dir.mkdir(parents=True)
    for name, content in (("HUBMonitor.exe", FAKE_EXE), ("winsw.exe", WINSW_STUB)):
        target = agent_dir / name
        target.write_text(content, encoding="utf-8")
        target.chmod(0o755)

    # Cada maquina tem o proprio ProgramData e o proprio papel.
    agent_program_data = work / "ProgramDataAgente"
    agent_program_data.mkdir()
    env_agent = {
        **env,
        "PROGRAMDATA": str(agent_program_data),
        "ProgramData": str(agent_program_data),
        "HUB_SERVICE_MARKER": str(work / "services-agent.txt"),
    }
    agent_run = run_once(shell, wrapper, agent_dir, 8443, env_agent, mode="agent")
    check("modo agente termina com codigo 0", agent_run.returncode == 0,
          (agent_run.stdout[-600:] + agent_run.stderr[-600:]))

    marcador_agente = work / "services-agent.txt"
    servicos_agente = (
        marcador_agente.read_text(encoding="utf-8") if marcador_agente.is_file() else ""
    )
    check("agente registra o servico", "failure HUBMonitorAgent" in servicos_agente, servicos_agente)
    check(
        "agente nao registra o servidor da loja",
        "failure HUBMonitorServer" not in servicos_agente,
        servicos_agente,
    )

    agent_env_file = agent_dir / ".env"
    check("agente grava .env", agent_env_file.is_file())
    if agent_env_file.is_file():
        agent_values = read_env(agent_env_file)
        check("agente grava MACHINE_NAME", agent_values.get("MACHINE_NAME") == "SERVIDOR-TESTE")
        check(
            "agente aponta CONNECTION_FILE para ProgramData",
            agent_values.get("CONNECTION_FILE", "").startswith(str(program_data)),
            agent_values.get("CONNECTION_FILE", ""),
        )
        check("agente nao grava SERVER_PORT", "SERVER_PORT" not in agent_values)

    agent_role = agent_program_data / "HUBMonitor" / "role.json"
    if agent_role.is_file():
        role = json.loads(agent_role.read_text(encoding="utf-8"))
        check("role.json do agente usa 8010", role.get("api_url") == "http://127.0.0.1:8010")

    print("\n== porta ocupada ==")
    import socket as _socket

    ocupada = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    ocupada.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
    ocupada.bind(("0.0.0.0", 8453))
    ocupada.listen(1)
    try:
        conflito_dir = work / "Program Files" / "Conflito"
        conflito_dir.mkdir(parents=True)
        for name, content in (("HUBMonitor.exe", FAKE_EXE), ("winsw.exe", WINSW_STUB)):
            target = conflito_dir / name
            target.write_text(content, encoding="utf-8")
            target.chmod(0o755)
        conflito = run_once(shell, wrapper, conflito_dir, 8453, env)
        check("porta ocupada falha com codigo 72", conflito.returncode == 72, str(conflito.returncode))
        check(
            "mensagem explica a porta ocupada",
            "em uso" in (conflito.stdout + conflito.stderr),
            (conflito.stdout + conflito.stderr)[-300:],
        )
    finally:
        ocupada.close()

    print("\n== desinstalacao ==")
    removal = run_once(shell, wrapper, install_dir, 8443, env, mode="server", action="remove")
    check("desinstalacao termina com codigo 0", removal.returncode == 0,
          (removal.stdout[-600:] + removal.stderr[-600:]))
    registros = marker.read_text(encoding="utf-8").splitlines()
    check(
        "backup desagendado na remocao",
        any(line.startswith("UNREGISTER|HUBMonitorBackup") for line in registros),
        str(registros),
    )

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
