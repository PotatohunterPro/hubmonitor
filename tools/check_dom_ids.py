"""Confere se todo id usado pelo JavaScript existe no HTML.

Um id trocado (ex.: telegramGroupId vs telegramChatId) nao quebra a
sintaxe: quebra a tela em tempo de execucao, so na maquina do cliente.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TELAS = [
    ROOT / "server" / "dashboard" / "templates" / "dashboard.html",
    ROOT / "server" / "dashboard" / "templates" / "configuration.html",
    ROOT / "desktop" / "ui" / "index.html",
]

DECLARADO = re.compile(r"""\bid=["']([A-Za-z0-9_-]+)["']""")
REFERENCIADO = re.compile(
    r"""(?:getElementById\(\s*["']([A-Za-z0-9_-]+)["']\s*\)|\$\(\s*["']([A-Za-z0-9_-]+)["']\s*\)|querySelector\(\s*["']#([A-Za-z0-9_-]+)["']\s*\))"""
)


def main() -> int:
    problemas = 0
    for tela in TELAS:
        texto = tela.read_text(encoding="utf-8")
        declarados = set(DECLARADO.findall(texto))
        referenciados = {grupo for achado in REFERENCIADO.findall(texto) for grupo in achado if grupo}
        faltando = sorted(referenciados - declarados)
        if faltando:
            problemas += len(faltando)
            print(f"  [FALHA] {tela.name}: {len(faltando)} id(s) usados e inexistentes")
            for nome in faltando:
                print(f"          - {nome}")
        else:
            print(f"  [PASS] {tela.name}: {len(referenciados)} id(s) conferem")
    print("")
    if problemas:
        print(f"RESULTADO: {problemas} referencia(s) quebrada(s)")
        return 1
    print("RESULTADO: todas as referencias de id existem")
    return 0


if __name__ == "__main__":
    sys.exit(main())
