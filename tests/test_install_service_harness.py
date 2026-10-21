"""Executa o bootstrap do servico com stubs (pulado sem PowerShell 7)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _powershell() -> str | None:
    for candidate in (shutil.which("pwsh"), str(ROOT / ".pwsh" / "pwsh")):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def test_bootstrap_do_servico_funciona_com_stubs():
    if _powershell() is None:
        pytest.skip("PowerShell 7 nao disponivel")

    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "verify_install_service.py")],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stdout[-2000:] + completed.stderr[-2000:]
    assert "todas as" in completed.stdout
