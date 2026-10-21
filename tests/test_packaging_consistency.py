"""Consistencia da cadeia de empacotamento (NSIS x build x servico).

Estes testes nao compilam o instalador (isso exige Windows), mas
garantem que os caminhos e os argumentos batem entre os arquivos. Sao
exatamente os defeitos que passam despercebidos ate o primeiro build.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NSIS_DIR = ROOT / "packaging" / "nsis"
NSIS = NSIS_DIR / "HUBMonitor.nsi"
BUILD = ROOT / "packaging" / "build_windows.ps1"
SERVICE = ROOT / "packaging" / "install-service.ps1"
SPEC = ROOT / "packaging" / "HUBMonitor.spec"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def nsis_define(name: str) -> str:
    match = re.search(r'!define\s+' + name + r'\s+"([^"]+)"', read(NSIS))
    assert match, f"define {name} ausente no NSIS"
    return match.group(1)


def resolve_from_nsis(relative: str) -> Path:
    cleaned = relative.replace("\\", "/")
    return (NSIS_DIR / cleaned).resolve()


def test_outfile_do_nsis_aponta_para_dist_do_repositorio():
    outfile = re.search(r'^OutFile\s+"([^"]+)"', read(NSIS), re.MULTILINE)
    assert outfile, "OutFile ausente"
    expected = (ROOT / "dist" / "HUBMonitor-Setup.exe").resolve()
    assert resolve_from_nsis(outfile.group(1)) == expected


def test_bundle_do_nsis_aponta_para_o_dist_do_pyinstaller():
    expected = (ROOT / "dist" / "HUBMonitor").resolve()
    assert resolve_from_nsis(nsis_define("BUNDLE_DIR")) == expected


def test_build_escreve_nos_mesmos_diretorios_que_o_nsis_le():
    build = read(BUILD)
    assert re.search(r"[$]Dist\s*=\s*Join-Path [$]Root 'dist'", build), "Dist diferente do esperado"
    assert re.search(r"[$]Bundle\s*=\s*Join-Path [$]Dist 'HUBMonitor'", build), "Bundle diferente do esperado"


def test_build_copia_os_arquivos_que_o_nsis_exige_no_bundle():
    build = read(BUILD)
    assert "install-service.ps1" in build and "Copy-Item" in build
    assert "MicrosoftEdgeWebView2RuntimeInstallerX64.exe" in build

    nsis = read(NSIS)
    assert '"$INSTDIR\\install-service.ps1"' in nsis
    assert '"$INSTDIR\\winsw.exe"' in nsis
    assert nsis_define("WEBVIEW2_INSTALLER") == "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
    assert "vendor\\" in nsis


def test_winsw_fica_na_raiz_do_bundle_como_o_servico_espera():
    build = read(BUILD)
    service = read(SERVICE)

    assert re.search(r"-Destination \(Join-Path [$]Bundle 'winsw\.exe'\)", build), (
        "o build deve copiar winsw.exe para a raiz do bundle"
    )
    assert "vendor\\winsw.exe" not in build, (
        "winsw nao pode ficar em vendor: o servico procura na raiz"
    )
    assert re.search(r"[$]WinSw\s*=\s*Join-Path [$]InstallDir 'winsw\.exe'", service)


def test_build_usa_o_instalador_offline_do_webview2():
    build = read(BUILD)
    assert "linkid=2124701" in build, "deve baixar o standalone, nao o bootstrapper online"
    assert "2124703" not in build, "bootstrapper online nao pode ser usado"
    assert "50MB" in build, "falta a guarda de tamanho contra o bootstrapper"


def service_parameters() -> set[str]:
    """Nomes dos parametros do script de servico.

    O bloco param() contem parenteses aninhados ([Parameter(...)]), entao
    o corte e feito ate a diretiva seguinte, nao ate o primeiro ")".
    """
    text = read(SERVICE)
    start = text.index("param(")
    end = text.index("Set-StrictMode", start)
    return set(re.findall(r"[$]([A-Za-z]\w*)", text[start:end]))


def test_nsis_passa_apenas_parametros_que_o_servico_aceita():
    text = read(SERVICE)
    nsis = read(NSIS)
    invocation = [line for line in nsis.splitlines() if "install-service.ps1" in line and "-Action install" in line]
    assert invocation, "NSIS nao chama install-service.ps1 -Action install"

    passed = set(re.findall(r"-(\w+)\s", invocation[0]))
    passed.discard("NoProfile")
    passed.discard("ExecutionPolicy")
    passed.discard("File")
    declared = service_parameters()
    missing = {name for name in passed if name not in declared}
    assert not missing, f"parametros nao declarados em install-service.ps1: {sorted(missing)}"


def test_servico_expoe_as_acoes_usadas_pelo_instalador():
    text = read(SERVICE)
    assert "ValidateSet('install', 'remove', 'import-connection')" in text
    nsis = read(NSIS)
    assert "-Action remove" in nsis


def test_executavel_tem_o_mesmo_nome_no_spec_e_no_nsis():
    assert 'name="HUBMonitor"' in read(SPEC)
    assert nsis_define("APP_EXE") == "HUBMonitor.exe"


def test_workflow_roda_o_mesmo_script_de_build():
    workflow = read(ROOT / ".github" / "workflows" / "build-windows.yml")
    assert "packaging/build_windows.ps1" in workflow
    assert "windows-latest" in workflow


def test_servico_verifica_saude_antes_de_declarar_sucesso():
    text = read(SERVICE)
    assert "-Uri ('https://127.0.0.1:' + $Port + '/health')" in text
    assert "Fail" in text
    # Falha de health precisa sair com codigo proprio, nao silenciar.
    assert "70" in text


def test_servico_nao_gera_certificado_novo_quando_ja_existe():
    text = read(SERVICE)
    assert "Test-Path -LiteralPath $ServerCert" in text
    assert "Certificado TLS existente preservado" in text


def test_servico_protege_env_e_chave_privada():
    text = read(SERVICE)
    assert "Restrict-File $EnvFile" in text
    assert "Restrict-File $ServerKey" in text
    assert "icacls" in text


def test_servico_preserva_token_existente():
    text = read(SERVICE)
    assert "AGENT_INGEST_TOKEN" in text
    assert "Credencial do agente preservada" in text


def test_porta_configurada_chega_ao_servidor_e_ao_firewall():
    text = read(SERVICE)
    assert "$envMap['SERVER_PORT'] = [string]$Port" in text
    assert "-LocalPort $Port" in text
