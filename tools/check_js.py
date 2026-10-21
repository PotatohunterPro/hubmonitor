"""Verifica a sintaxe do JavaScript embutido nas telas.

O painel e as janelas nunca tiveram o JS executado. Este utilitario
extrai os blocos <script> dos templates, remove as expressoes Jinja e
roda "node --check" em cada um.

Uso: python tools/check_js.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TELAS = [
    ROOT / "desktop" / "ui" / "index.html",
    ROOT / "server" / "dashboard" / "templates" / "dashboard.html",
    ROOT / "server" / "dashboard" / "templates" / "configuration.html",
]

NODE_CANDIDATOS = [
    os.environ.get("NODE_BIN", ""),
    shutil.which("node") or "",
    "/Users/wellington/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node",
]

BLOCO = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)
JINJA_EXPR = re.compile(r"{{.*?}}", re.S)
JINJA_TAG = re.compile(r"{%.*?%}", re.S)


def node() -> str | None:
    for candidate in NODE_CANDIDATOS:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def blocos(texto: str) -> list[str]:
    partes = []
    for bloco in BLOCO.findall(texto):
        limpo = JINJA_EXPR.sub("null", bloco)
        limpo = JINJA_TAG.sub("", limpo)
        if limpo.strip():
            partes.append(limpo)
    return partes


def main() -> int:
    executor = node()
    if executor is None:
        print("node nao encontrado; nada a fazer")
        return 0

    falhas = 0
    total = 0
    with tempfile.TemporaryDirectory() as tmp:
        for tela in TELAS:
            if not tela.is_file():
                print(f"  [FALHA] {tela.name}: arquivo ausente")
                falhas += 1
                continue
            for indice, codigo in enumerate(blocos(tela.read_text(encoding="utf-8"))):
                total += 1
                alvo = Path(tmp) / f"{tela.stem}-{indice}.js"
                alvo.write_text(codigo, encoding="utf-8")
                resultado = subprocess.run(
                    [executor, "--check", str(alvo)],
                    capture_output=True, text=True, timeout=60,
                )
                if resultado.returncode == 0:
                    print(f"  [PASS] {tela.name} bloco {indice}")
                else:
                    falhas += 1
                    print(f"  [FALHA] {tela.name} bloco {indice}")
                    print((resultado.stderr or "").strip()[:800])

    print("")
    if falhas:
        print(f"RESULTADO: {falhas} bloco(s) com erro de sintaxe")
        return 1
    print(f"RESULTADO: {total} bloco(s) de JavaScript validos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
