"""Analise estrutural do script NSIS.

Nao substitui a compilacao (que exige Windows), mas pega os erros que
quebram o build por estrutura: blocos desbalanceados, label inexistente
e define duplicado.
"""

from __future__ import annotations

import re
from pathlib import Path

NSIS = Path(__file__).resolve().parents[1] / "packaging" / "nsis" / "HUBMonitor.nsi"


def text() -> str:
    return NSIS.read_text(encoding="utf-8")


def test_blocos_function_balanceados():
    source = text()
    assert len(re.findall(r"^Function\s+", source, re.MULTILINE)) == len(
        re.findall(r"^FunctionEnd\s*$", source, re.MULTILINE)
    )


def test_blocos_section_balanceados():
    source = text()
    assert len(re.findall(r"^Section\b", source, re.MULTILINE)) == len(
        re.findall(r"^SectionEnd\s*$", source, re.MULTILINE)
    )


def test_if_endif_balanceados():
    source = text()
    aberturas = len(re.findall(r"\$\{If\}", source)) + len(re.findall(r"\$\{IfNot\}", source))
    fechamentos = len(re.findall(r"\$\{EndIf\}", source))
    assert aberturas > 0
    assert aberturas == fechamentos, f"If/EndIf desbalanceados: {aberturas} x {fechamentos}"


def test_labels_de_goto_existem():
    source = text()
    labels = set(re.findall(r"^\s*([A-Za-z_]\w*):\s*$", source, re.MULTILINE))
    alvos = set(re.findall(r"\bGoto\s+([A-Za-z_]\w*)", source))
    assert not (alvos - labels), f"Goto para label inexistente: {sorted(alvos - labels)}"


def test_labels_de_messagebox_existem():
    source = text()
    labels = set(re.findall(r"^\s*([A-Za-z_]\w*):\s*$", source, re.MULTILINE))
    alvos = set(re.findall(r"\bID(?:NO|YES|CANCEL|RETRY)\s+([A-Za-z_]\w*)", source))
    assert not (alvos - labels), f"salto para label inexistente: {sorted(alvos - labels)}"


def test_defines_sem_duplicidade():
    nomes = re.findall(r"^!define\s+(\w+)", text(), re.MULTILINE)
    duplicados = {nome for nome in nomes if nomes.count(nome) > 1}
    assert not duplicados, f"defines duplicados: {sorted(duplicados)}"


def test_instalador_nao_usa_caminho_absoluto_pessoal():
    source = text()
    for proibido in ("/Users/", "C:\\Users\\"):
        assert proibido not in source


def test_webview2_e_offline_e_nao_bootstrapper():
    source = text()
    assert "MicrosoftEdgeWebView2RuntimeInstallerX64.exe" in source
    assert "MicrosoftEdgeWebview2Setup.exe" not in source


def test_falha_do_servico_aborta_a_instalacao():
    source = text()
    bloco = source[source.index("install-service.ps1") : source.index("WriteRegStr HKLM")]
    assert "Abort" in bloco
    assert "MB_ICONSTOP" in bloco
