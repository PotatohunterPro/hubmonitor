"""Persistencia atomica das configuracoes editaveis pelo painel local."""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path

from dotenv import dotenv_values


def _quote_env(value: str) -> str:
    if "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError("A configuracao contem caracteres nao permitidos.")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fiscal_target_from_settings(settings):
    """Destino fiscal persistido no .env — fonte de verdade unica.

    Existe porque a pagina de configuracao grava no arquivo sem atualizar
    os.environ do processo: ler o ambiente devolveria o valor anterior.
    Um unico lugar evita que a exportacao e o painel divirjam.
    """
    from dotenv import dotenv_values

    from shared import fiscal as fiscal_mod

    valores: dict[str, str] = {}
    if getattr(settings, "env_file", None) is not None:
        try:
            valores = {
                chave: valor
                for chave, valor in dotenv_values(settings.env_file).items()
                if valor is not None
            }
        except OSError:
            valores = {}
    return fiscal_mod.from_env(valores) or fiscal_mod.from_env(os.environ)


def restart_local_agent() -> bool:
    """Reinicia o agente desta maquina para aplicar configuracao nova.

    O agente le FISCAL_*/SEFAZ_* ao iniciar. Sem reiniciar, o proprio
    servidor continua mostrando a SEFAZ como "sem dados" depois de o
    operador configurar o destino fiscal.
    """
    if os.name != "nt":
        return False
    reiniciado = False
    for action in ("stop", "start"):
        try:
            completed = subprocess.run(
                ["sc.exe", action, "HUBMonitorAgent"],
                capture_output=True,
                timeout=30,
            )
            reiniciado = reiniciado or completed.returncode == 0
        except (OSError, subprocess.SubprocessError):
            pass
        time.sleep(2)
    return reiniciado


def _restrict_file(path: Path) -> None:
    if os.name == "nt":
        subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                "*S-1-5-18:(F)",
                "*S-1-5-32-544:(F)",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        path.chmod(0o600)


def save_env_values(path: Path | None, updates: dict[str, str]) -> None:
    if path is None:
        raise ValueError("O arquivo de configuracao da loja nao foi localizado.")
    if not path.is_file():
        raise ValueError("O arquivo de configuracao da loja nao existe.")

    values = {
        key: (value if value is not None else "")
        for key, value in dotenv_values(path, interpolate=False).items()
    }
    values.update(updates)
    text = "\n".join(f"{key}={_quote_env(str(value))}" for key, value in sorted(values.items())) + "\n"

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        _restrict_file(temporary)
        os.replace(temporary, path)
        _restrict_file(path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def apply_windows_firewall_subnet(local_subnet: str, port: int) -> None:
    """Mantem a regra da API restrita a rede privada informada pelo operador."""
    if os.name != "nt":
        return
    script = (
        "$ErrorActionPreference='Stop'; "
        "$rule=Get-NetFirewallRule -DisplayName 'Bertolo Monitor API' "
        "-ErrorAction SilentlyContinue; "
        "if ($null -eq $rule) { "
        f"New-NetFirewallRule -DisplayName 'Bertolo Monitor API' -Direction Inbound "
        f"-Action Allow -Protocol TCP -LocalPort {int(port)} "
        f"-RemoteAddress '{local_subnet}' -Profile Any | Out-Null "
        "} else { "
        f"$rule | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter "
        f"-RemoteAddress '{local_subnet}'; "
        f"$rule | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter "
        f"-Protocol TCP -LocalPort {int(port)} "
        "}; exit 0"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
    )
