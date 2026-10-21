#Requires -Version 5.1
<#
.SYNOPSIS
    Verifica o ambiente ANTES do build do instalador.

.DESCRIPTION
    Roda em segundos e falha cedo: Python, modulos, NSIS, layout do
    repositorio, artefatos de terceiros e espaco em disco. Evita
    descobrir um problema depois de minutos de PyInstaller.

    Pode ser executado fora do Windows: os testes especificos de Windows
    sao marcados como NAO VERIFICADO em vez de falharem.

.EXAMPLE
    pwsh -File packaging/preflight-windows.ps1 -Python .venv/bin/python -SkipNsis
#>
[CmdletBinding()]
param(
    [string]$Python = 'python',
    [switch]$SkipNsis,
    [switch]$RequireVendor
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$IsWindowsHost = ($env:OS -eq 'Windows_NT')

$script:Failures = 0
$script:Checks = 0

function Add-Result {
    param(
        [string]$Label,
        [string]$Status,   # OK | FALHA | --
        [string]$Detail = ''
    )
    $script:Checks++
    if ($Status -eq 'FALHA') { $script:Failures++ }
    $color = 'Gray'
    if ($Status -eq 'OK') { $color = 'Green' }
    if ($Status -eq 'FALHA') { $color = 'Red' }
    Write-Host ('  [' + $Status.PadRight(5) + '] ' + $Label + ' ' + $Detail) -ForegroundColor $color
}

Write-Host ''
Write-Host '  HUB MONITORAMENTO - PREFLIGHT DO BUILD' -ForegroundColor Cyan
Write-Host ('  Raiz: ' + $Root)
Write-Host ''

# ---------------------------------------------------------------------
Write-Host 'Ambiente' -ForegroundColor White
if ($IsWindowsHost) {
    Add-Result 'Windows' 'OK' ($env:OS)
} else {
    Add-Result 'Windows' '--' 'execucao fora do Windows; checks de Windows serao ignorados'
}
Add-Result 'PowerShell' 'OK' $PSVersionTable.PSVersion.ToString()

if ($IsWindowsHost) {
    if ([Environment]::Is64BitOperatingSystem) {
        Add-Result 'Sistema 64 bits' 'OK'
    } else {
        Add-Result 'Sistema 64 bits' 'FALHA' 'somente x64'
    }
}

# ---------------------------------------------------------------------
Write-Host ''
Write-Host 'Python' -ForegroundColor White
$previous = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $version = & $Python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>&1
    $versionOk = ($LASTEXITCODE -eq 0)
} finally {
    $ErrorActionPreference = $previous
}
if (-not $versionOk) {
    Add-Result 'Interpretador' 'FALHA' ('nao executou: ' + $Python)
} else {
    $texto = ([string]($version | Out-String)).Trim()
    if ([version]$texto -ge [version]'3.12') {
        Add-Result 'Versao' 'OK' $texto
    } else {
        Add-Result 'Versao' 'FALHA' ($texto + ' (minimo 3.12)')
    }
}

$modules = @('PyInstaller', 'fastapi', 'uvicorn', 'cryptography', 'PIL')
if ($IsWindowsHost) {
    $modules += @('webview', 'pystray', 'clr_loader', 'pythonnet')
}
foreach ($module in $modules) {
    $ErrorActionPreference = 'Continue'
    & $Python -c ('import ' + $module) 2>&1 | Out-Null
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previous
    if ($code -eq 0) {
        Add-Result ('modulo ' + $module) 'OK'
    } else {
        Add-Result ('modulo ' + $module) 'FALHA' 'instale com: pip install -r requirements-dev.txt'
    }
}

# ---------------------------------------------------------------------
Write-Host ''
Write-Host 'Repositorio' -ForegroundColor White
$required = @(
    (Join-Path 'packaging' 'entry.py'),
    (Join-Path 'packaging' 'HUBMonitor.spec'),
    (Join-Path 'packaging' 'install-service.ps1'),
    (Join-Path (Join-Path 'packaging' 'nsis') 'HUBMonitor.nsi'),
    (Join-Path 'packaging' 'hubmonitor.ico'),
    (Join-Path (Join-Path 'desktop' 'ui') 'index.html'),
    (Join-Path (Join-Path (Join-Path 'server' 'dashboard') 'templates') 'dashboard.html'),
    (Join-Path 'certs' 'icp-brasil-roots.pem')
)
foreach ($relative in $required) {
    $full = Join-Path $Root $relative
    if (Test-Path -LiteralPath $full) {
        Add-Result $relative 'OK'
    } else {
        Add-Result $relative 'FALHA' 'arquivo ausente'
    }
}

# ---------------------------------------------------------------------
Write-Host ''
Write-Host 'NSIS' -ForegroundColor White
if ($SkipNsis) {
    Add-Result 'makensis' '--' 'ignorado (-SkipNsis)'
} elseif (-not $IsWindowsHost) {
    Add-Result 'makensis' '--' 'nao avaliado fora do Windows'
} else {
    $makeNsis = $null
    foreach ($candidate in @('C:\Program Files (x86)\NSIS\makensis.exe', 'C:\Program Files\NSIS\makensis.exe')) {
        if (Test-Path -LiteralPath $candidate) { $makeNsis = $candidate; break }
    }
    if ($makeNsis) {
        Add-Result 'makensis' 'OK' $makeNsis
    } else {
        Add-Result 'makensis' 'FALHA' 'instale o NSIS 3.x'
    }
}

# ---------------------------------------------------------------------
Write-Host ''
Write-Host 'Artefatos de terceiros' -ForegroundColor White
$vendor = Join-Path $PSScriptRoot 'vendor'
$winsw = Join-Path $vendor 'winsw.exe'
$webview = Join-Path $vendor 'MicrosoftEdgeWebView2RuntimeInstallerX64.exe'

if (Test-Path -LiteralPath $winsw) {
    Add-Result 'winsw.exe' 'OK'
} elseif ($RequireVendor) {
    Add-Result 'winsw.exe' 'FALHA' 'baixe antes do build'
} else {
    Add-Result 'winsw.exe' '--' 'sera baixado no build'
}

if (Test-Path -LiteralPath $webview) {
    $mb = [math]::Round((Get-Item -LiteralPath $webview).Length / 1MB, 1)
    if ($mb -lt 50) {
        Add-Result 'WebView2 offline' 'FALHA' ($mb.ToString() + ' MB: parece o bootstrapper online')
    } else {
        Add-Result 'WebView2 offline' 'OK' ($mb.ToString() + ' MB')
    }
} elseif ($RequireVendor) {
    Add-Result 'WebView2 offline' 'FALHA' 'baixe o Standalone Installer x64'
} else {
    Add-Result 'WebView2 offline' '--' 'sera baixado no build'
}

# ---------------------------------------------------------------------
Write-Host ''
Write-Host 'Disco' -ForegroundColor White
try {
    if ($IsWindowsHost) {
        $qualifier = (Split-Path -Qualifier $Root).TrimEnd(':')
        $free = (Get-PSDrive -Name $qualifier -ErrorAction Stop).Free
    } else {
        # Fora do Windows nao existe qualificador; usa a unidade do caminho.
        $free = (Get-Item -LiteralPath $Root).PSDrive.Free
    }
    $freeGb = [math]::Round($free / 1GB, 1)
    if ($freeGb -ge 2) {
        Add-Result 'Espaco livre' 'OK' ($freeGb.ToString() + ' GB')
    } else {
        Add-Result 'Espaco livre' 'FALHA' ($freeGb.ToString() + ' GB (minimo 2 GB)')
    }
} catch {
    Add-Result 'Espaco livre' '--' 'nao foi possivel medir'
}

# ---------------------------------------------------------------------
Write-Host ''
if ($script:Failures -gt 0) {
    Write-Host ('RESULTADO: ' + $script:Failures + ' de ' + $script:Checks + ' verificacoes falharam.') -ForegroundColor Red
    exit 1
}
Write-Host ('RESULTADO: ' + $script:Checks + ' verificacoes sem falha.') -ForegroundColor Green
exit 0
