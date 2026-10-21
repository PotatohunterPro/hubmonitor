# -*- mode: python ; coding: utf-8 -*-
"""Receita PyInstaller do HUB Monitoramento.

Gera um unico executavel (onedir) que atende os dois papeis:

    HUBMonitor.exe ui / agent / server / export-connection

Uso (no Windows):
    pyinstaller packaging/HUBMonitor.spec --noconfirm --clean
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(ROOT / "server" / "dashboard"), "server/dashboard"),
    (str(ROOT / "desktop" / "ui"), "desktop/ui"),
    (str(ROOT / "certs"), "certs"),
]
binaries = []
hiddenimports = [
    "psutil",
    "dns.asyncresolver",
    "jinja2",
    "pystray._win32",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "PIL._tkinter_finder",
]

# pywebview no Windows depende do .NET via pythonnet/clr-loader.
# Sao opcionais no build (nao existem no macOS), mas obrigatorios no Windows.
if sys.platform == "win32":
    hiddenimports += [
        "clr_loader",
        "pythonnet",
        "System",
        "System.Windows.Forms",
        "Microsoft.Web.WebView2",
    ]

for package in ("uvicorn", "fastapi", "librouteros", "webview", "pystray"):
    try:
        collected = collect_all(package)
    except Exception:  # noqa: BLE001 - pacote ausente nao deve quebrar o build
        continue
    datas += collected[0]
    binaries += collected[1]
    hiddenimports += collected[2]

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pandas", "numpy", "scipy"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HUBMonitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "packaging" / "hubmonitor.ico")
    if (ROOT / "packaging" / "hubmonitor.ico").is_file()
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="HUBMonitor",
)
