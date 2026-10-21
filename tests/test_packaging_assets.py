"""Ativos de empacotamento: icone, imagens e dependencias declaradas."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_icone_do_executavel_existe_com_tamanhos_padrao():
    pytest.importorskip("PIL")
    from PIL import Image

    path = ROOT / "packaging" / "hubmonitor.ico"
    assert path.is_file(), "o build precisa de packaging/hubmonitor.ico"

    image = Image.open(path)
    tamanhos = {largura for largura, altura in image.info.get("sizes", [])}
    assert {16, 32, 48, 256} <= tamanhos, f"tamanhos presentes: {sorted(tamanhos)}"


def test_spec_aponta_para_o_icone():
    spec = (ROOT / "packaging" / "HUBMonitor.spec").read_text(encoding="utf-8")
    assert "hubmonitor.ico" in spec


def test_imagens_da_bandeja_existem():
    assert (ROOT / "desktop" / "ui" / "hubmonitor.png").is_file()
    assert (ROOT / "desktop" / "ui" / "hubmonitor-64.png").is_file()


def test_requirements_dev_inclui_as_dependencias_do_desktop():
    dev = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "requirements-desktop.txt" in dev

    desktop = (ROOT / "requirements-desktop.txt").read_text(encoding="utf-8")
    for pacote in ("pywebview", "pystray", "pillow"):
        assert pacote in desktop
    # No macOS/Linux nao queremos pyobjc/GTK no ambiente de testes.
    assert 'sys_platform == "win32"' in desktop


def test_workflow_instala_a_partir_do_requirements_dev():
    workflow = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
    assert "-r requirements-dev.txt" in workflow

def _powershell() -> str | None:
    import shutil

    for candidate in (shutil.which("pwsh"), str(ROOT / ".pwsh" / "pwsh")):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def test_preflight_do_build_executa_sem_falhas():
    """Roda o preflight de verdade (pulado se nao houver PowerShell 7)."""
    import subprocess

    pwsh = _powershell()
    if pwsh is None:
        pytest.skip("PowerShell 7 nao disponivel")

    venv_python = ROOT / ".venv" / "bin" / "python"
    interpreter = str(venv_python) if venv_python.is_file() else "python"

    completed = subprocess.run(
        [
            pwsh, "-NoProfile", "-File",
            str(ROOT / "packaging" / "preflight-windows.ps1"),
            "-Python", interpreter, "-SkipNsis",
        ],
        capture_output=True, text=True, timeout=240,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "sem falha" in completed.stdout


def test_build_chama_o_preflight():
    build = (ROOT / "packaging" / "build_windows.ps1").read_text(encoding="utf-8")
    assert "preflight-windows.ps1" in build
    assert "Preflight reprovado" in build

def test_spec_nao_usa_marcador_de_ambiente_em_is_module_satisfies():
    """is_module_satisfies espera requisito, nao marcador (quebra o build)."""
    spec = (ROOT / "packaging" / "HUBMonitor.spec").read_text(encoding="utf-8")
    assert "is_module_satisfies" not in spec
    assert 'sys.platform == "win32"' in spec


def test_spec_inclui_os_recursos_que_a_interface_precisa():
    spec = (ROOT / "packaging" / "HUBMonitor.spec").read_text(encoding="utf-8")
    for recurso in ("server/dashboard", "desktop/ui", "certs"):
        assert recurso in spec.replace("\\", "/")

def test_script_de_validacao_referencia_arquivos_reais():
    script = (ROOT / "packaging" / "validar-no-windows.ps1").read_text(encoding="utf-8")
    for nome in ("preflight-windows.ps1", "build_windows.ps1", "smoke_bundle.py", "e2e_https_test.py"):
        assert nome in script
        assert list(ROOT.rglob(nome)), nome
    assert "HUBMonitor-Setup.exe" in script
    assert "BUILD-INFO.json" in script


def test_script_de_validacao_mostra_o_plano_fora_do_windows():
    import subprocess

    pwsh = _powershell()
    if pwsh is None:
        pytest.skip("PowerShell 7 nao disponivel")

    completed = subprocess.run(
        [pwsh, "-NoProfile", "-File", str(ROOT / "packaging" / "validar-no-windows.ps1")],
        capture_output=True, text=True, timeout=120,
    )
    # Fora do Windows o script apenas mostra o plano e sai com 2.
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "PLANO DE VALIDACAO" in completed.stdout
    for etapa in ("Preflight", "Testes", "Build", "Bundle", "HTTPS"):
        assert etapa in completed.stdout

def _node_bin() -> str | None:
    import os
    import shutil

    candidatos = [
        shutil.which("node"),
        os.environ.get("NODE_BIN"),
        "/Users/wellington/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node",
    ]
    for candidato in candidatos:
        if candidato and Path(candidato).is_file():
            return candidato
    return None


def test_ui_render_executa_nos_tres_cenarios():
    """Roda o render() da janela num DOM falso (pulado sem Node)."""
    import subprocess
    import sys

    if _node_bin() is None:
        pytest.skip("Node indisponivel")

    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_ui_render.py")],
        capture_output=True, text=True, timeout=180,
    )
    assert completed.returncode == 0, completed.stdout[-1500:] + completed.stderr[-1500:]
    assert "tres cenarios" in completed.stdout


def test_javascript_das_telas_tem_sintaxe_valida():
    import subprocess
    import sys

    if _node_bin() is None:
        pytest.skip("Node indisponivel")

    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_js.py")],
        capture_output=True, text=True, timeout=180,
    )
    assert completed.returncode == 0, completed.stdout[-1500:] + completed.stderr[-1500:]

def test_tela_de_configuracao_executa_com_fetch_falso():
    """Carrega as configuracoes no formulario (pulado sem Node)."""
    import subprocess
    import sys

    if _node_bin() is None:
        pytest.skip("Node indisponivel")

    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_config_page.py")],
        capture_output=True, text=True, timeout=180,
    )
    assert completed.returncode == 0, completed.stdout[-1500:] + completed.stderr[-1500:]
    assert "carregou, salvou e testou" in completed.stdout


def test_ids_do_javascript_existem_no_html():
    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_dom_ids.py")],
        capture_output=True, text=True, timeout=120,
    )
    assert completed.returncode == 0, completed.stdout[-1500:] + completed.stderr[-1500:]

def test_painel_renderiza_todas_as_secoes():
    """Executa matriz, WANs, ocorrencias, eventos e grafico (pulado sem Node)."""
    import subprocess
    import sys

    if _node_bin() is None:
        pytest.skip("Node indisponivel")

    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_dashboard.py")],
        capture_output=True, text=True, timeout=180,
    )
    assert completed.returncode == 0, completed.stdout[-1500:] + completed.stderr[-1500:]
    assert "renderizou todas as secoes" in completed.stdout

def test_todo_diagnostico_tem_rotulo_na_tela():
    """Constante de diagnostico sem rotulo aparece crua para o operador."""
    from shared import constants as C

    html = (ROOT / "server" / "dashboard" / "templates" / "dashboard.html").read_text(encoding="utf-8")
    bloco = html.split("var diagnosisLabels = {", 1)[1].split("};", 1)[0]
    rotulos = set(re.findall(r"'([^']+)'\s*:", bloco))

    codigos = {
        valor
        for nome, valor in vars(C).items()
        if nome.startswith("DIAG_") and nome != "DIAG_AUTH_AFTER_CONNECTION"
    }
    faltando = sorted(codigos - rotulos)
    assert not faltando, f"sem rotulo na tela: {faltando}"


def test_todo_componente_tem_rotulo():
    from shared import constants as C

    componentes = {
        valor
        for nome, valor in vars(C).items()
        if nome.startswith("COMPONENT_") and isinstance(valor, str) and nome != "COMPONENT_LABELS"
    }
    faltando = sorted(componentes - set(C.COMPONENT_LABELS))
    assert not faltando, f"sem rotulo: {faltando}"

def test_requisitos_estao_fixados_para_build_reproduzivel():
    """Versao solta (>=) gera binarios diferentes a cada build."""
    import re

    soltos = []
    for nome in ("requirements-server.txt", "requirements-agent.txt", "requirements-dev.txt"):
        for linha in (ROOT / nome).read_text(encoding="utf-8").splitlines():
            texto = linha.strip()
            if not texto or texto.startswith("#") or texto.startswith("-r"):
                continue
            if "==" not in texto:
                soltos.append((nome, texto))
    assert not soltos, f"sem versao fixa: {soltos}"

    # Excecao documentada: pacotes so do Windows, resolvidos no build.
    desktop = (ROOT / "requirements-desktop.txt").read_text(encoding="utf-8")
    for pacote in ("pywebview", "pystray", "pythonnet", "clr-loader"):
        assert re.search(pacote + r">=.*sys_platform", desktop)


def test_versoes_fixadas_estao_instaladas():
    """O pin precisa corresponder ao ambiente onde a suite passou."""
    import importlib.metadata as metadata
    import re

    conferidos = 0
    for nome in ("requirements-server.txt", "requirements-agent.txt"):
        for linha in (ROOT / nome).read_text(encoding="utf-8").splitlines():
            achado = re.match(r"^([A-Za-z0-9_.-]+)(\[[^\]]+\])?==([^\s;]+)", linha.strip())
            if not achado:
                continue
            pacote, versao = achado.group(1), achado.group(3)
            instalada = metadata.version(pacote)
            assert instalada == versao, f"{pacote}: pin {versao}, instalado {instalada}"
            conferidos += 1
    assert conferidos >= 12


def test_build_registra_o_pip_freeze():
    build = (ROOT / "packaging" / "build_windows.ps1").read_text(encoding="utf-8")
    assert "pip freeze" in build
    assert "pip_freeze" in build

def test_intervalos_documentados_batem_com_o_codigo():
    """O guia precisa citar os intervalos reais, nao numeros de memoria."""
    from shared import constants as C

    guia = (ROOT / "docs" / "GUIA_INSTALACAO.md").read_text(encoding="utf-8")
    secao = guia.split("## 5c.", 1)[1].split("## 5b.", 1)[0]

    documentados = {int(valor) for valor in re.findall(r"\|\s*(\d+)\s*s\s*\|", secao)}
    reais = {int(valor) for valor in C.DEFAULT_INTERVALS.values()}
    reais.add(int(C.SENDER_INTERVAL_SECONDS))

    assert documentados == reais, f"guia {sorted(documentados)} != codigo {sorted(reais)}"
    assert f"{C.INCIDENT_FAILURE_THRESHOLD} falhas consecutivas" in secao
    assert f"{C.INCIDENT_RECOVERY_THRESHOLD} sucessos consecutivos" in secao
    assert "45 s" in secao

def test_versao_do_produto_e_unica():
    """VERSION, pyproject, agente e servidor precisam dizer o mesmo numero."""
    from shared import constants as C

    version_arquivo = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    achado = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    assert achado, "pyproject sem version"

    assert achado.group(1) == version_arquivo, "pyproject != VERSION"
    assert C.AGENT_VERSION == version_arquivo, "agente reporta versao diferente"
    assert C.SERVER_VERSION == version_arquivo, "servidor reporta versao diferente"

def test_env_example_cobre_as_chaves_lidas_pelo_codigo():
    """Chave lida pelo codigo e ausente do exemplo vira configuracao invisivel."""
    import re as _re

    exemplo = set()
    for linha in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        texto = linha.strip()
        if texto and not texto.startswith("#") and "=" in texto:
            exemplo.add(texto.split("=", 1)[0].strip())

    usadas = set()
    for nome in ("server/config.py", "agent/config.py"):
        texto = (ROOT / nome).read_text(encoding="utf-8")
        usadas |= set(_re.findall(r'_env[a-z_]*\(\s*"([A-Z0-9_]+)"', texto))

    faltando = sorted(usadas - exemplo)
    assert not faltando, f"faltam no .env.example: {faltando}"

    # Chaves fiscais sao lidas por shared/fiscal.py, fora do padrao _env().
    for chave in ("FISCAL_UF", "FISCAL_DOCUMENT", "FISCAL_ENDPOINT_CONFIRMED"):
        assert chave in exemplo, f"{chave} fora do .env.example"


def test_env_example_usa_a_porta_atual():
    texto = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "SERVER_PORT=8443" in texto
    assert "SERVER_URL=https://192.168.0.110:8443" in texto

def test_versao_do_instalador_vem_do_build():
    """NSIS com versao fixa divergiria do BUILD-INFO."""
    nsi = (ROOT / "packaging" / "nsis" / "HUBMonitor.nsi").read_text(encoding="utf-8")
    assert "!ifndef APP_VERSION" in nsi

    build = (ROOT / "packaging" / "build_windows.ps1").read_text(encoding="utf-8")
    assert "/DAPP_VERSION=" in build

def test_documento_historico_avisa_que_nao_e_o_produto_atual():
    texto = (ROOT / "PLANO_ACAO_WINDOWS.md").read_text(encoding="utf-8")
    cabecalho = texto[:900]
    assert "histórico" in cabecalho.lower()
    assert "8443" in cabecalho
    assert "HUBMonitorAgent" in cabecalho
    # A frase antiga afirmava que os nomes Bertolo continuavam nos servicos.
    assert "permanece nos serviços" not in texto

def test_build_recusa_versao_diferente_da_declarada():
    script = (ROOT / "packaging" / "validar-no-windows.ps1").read_text(encoding="utf-8")
    assert "$declarada" in script
    assert "difere de VERSION" in script
