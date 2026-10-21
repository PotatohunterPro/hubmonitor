#Requires -Version 5.1
<#
.SYNOPSIS
    Gera o HUBMonitor-Setup.exe (ambiente Windows obrigatorio).

.DESCRIPTION
    Etapas:
      1. confere as dependencias de build;
      2. baixa (uma vez, no build) o WinSW e o bootstrapper do WebView2;
      3. gera o executavel com PyInstaller;
      4. gera o instalador com NSIS;
      5. calcula o SHA-256 e grava o relatorio do build.

    O computador do cliente NAO baixa nada: tudo vai dentro do pacote.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\packaging\build_windows.ps1
#>
[CmdletBinding()]
param(
    [string]$Python = 'python',
    [string]$Version = '1.0.0',
    [switch]$SkipInstaller,
    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Vendor = Join-Path $PSScriptRoot 'vendor'
$Dist = Join-Path $Root 'dist'
$Build = Join-Path $Root 'build'
$Bundle = Join-Path $Dist 'HUBMonitor'

Write-Host ''
Write-Host '  HUB MONITORAMENTO - BUILD DO INSTALADOR' -ForegroundColor Cyan
Write-Host ('  Versao : ' + $Version)
Write-Host ('  Raiz   : ' + $Root)
Write-Host ''

function Invoke-Checked {
    param([string]$FilePath, [string[]]$Arguments)
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('Falhou (' + $LASTEXITCODE + '): ' + $FilePath) }
}

# ---------------------------------------------------------------------
Write-Host '==> Preflight' -ForegroundColor Cyan
$preflightArgs = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass',
    '-File', (Join-Path $PSScriptRoot 'preflight-windows.ps1'),
    '-Python', $Python
)
if ($SkipInstaller) { $preflightArgs += '-SkipNsis' }
& powershell.exe @preflightArgs
if ($LASTEXITCODE -ne 0) {
    throw 'Preflight reprovado. Corrija os itens marcados como FALHA antes de continuar.'
}

# ---------------------------------------------------------------------
Write-Host '==> Dependencias' -ForegroundColor Cyan
$required = @('PyInstaller', 'webview', 'pystray', 'PIL', 'cryptography', 'fastapi', 'uvicorn')
if ($env:OS -eq 'Windows_NT') {
    # pywebview usa o WebView2 via pythonnet/clr-loader no Windows.
    $required += @('clr_loader', 'pythonnet')
}
foreach ($module in $required) {
    & $Python -c ('import ' + $module) 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw ('Modulo ausente no Python de build: ' + $module + '. Rode: pip install -r requirements-dev.txt pywebview pystray pythonnet clr-loader')
    }
    Write-Host ('    ok: ' + $module)
}

$MakeNsis = $null
foreach ($candidate in @(
    'C:\Program Files (x86)\NSIS\makensis.exe',
    'C:\Program Files\NSIS\makensis.exe'
)) {
    if (Test-Path -LiteralPath $candidate) { $MakeNsis = $candidate; break }
}
if (-not $SkipInstaller -and -not $MakeNsis) {
    throw 'makensis.exe nao encontrado. Instale o NSIS 3.x (https://nsis.sourceforge.io).'
}
if ($MakeNsis) { Write-Host ('    ok: ' + $MakeNsis) }

# ---------------------------------------------------------------------
Write-Host ''
Write-Host '==> Artefatos de terceiros (baixados no build)' -ForegroundColor Cyan
New-Item -ItemType Directory -Path $Vendor -Force | Out-Null

$WinSwPath = Join-Path $Vendor 'winsw.exe'
if (-not (Test-Path -LiteralPath $WinSwPath)) {
    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/winsw/winsw/releases/latest' -UseBasicParsing -TimeoutSec 30
    $asset = $release.assets | Where-Object { $_.name -eq 'WinSW-x64.exe' } | Select-Object -First 1
    if (-not $asset) { throw 'Asset WinSW-x64.exe nao encontrado no release.' }
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $WinSwPath -UseBasicParsing -TimeoutSec 180
    Write-Host ('    WinSW ' + $release.tag_name + ' baixado')
} else {
    Write-Host '    WinSW ja presente'
}

# Evergreen STANDALONE Installer (offline). O bootstrapper ~2 MB baixa o
# runtime do cliente, o que o pedido proibe; o standalone ja traz tudo.
$WebView2Path = Join-Path $Vendor 'MicrosoftEdgeWebView2RuntimeInstallerX64.exe'
if (-not (Test-Path -LiteralPath $WebView2Path)) {
    Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/?linkid=2124701' -OutFile $WebView2Path -UseBasicParsing -TimeoutSec 900
}
$webViewBytes = (Get-Item -LiteralPath $WebView2Path).Length
if ($webViewBytes -lt 50MB) {
    throw ('O arquivo do WebView2 tem ' + [math]::Round($webViewBytes / 1MB, 1) + ' MB e parece ser o bootstrapper ONLINE. Baixe o Evergreen Standalone Installer x64 e salve em ' + $WebView2Path)
}
Write-Host ('    WebView2 offline (' + [math]::Round($webViewBytes / 1MB, 1) + ' MB)')

# ---------------------------------------------------------------------
Write-Host ''
Write-Host '==> PyInstaller' -ForegroundColor Cyan
$pyInstallerArgs = @('-m', 'PyInstaller', (Join-Path $PSScriptRoot 'HUBMonitor.spec'), '--noconfirm', '--distpath', $Dist, '--workpath', (Join-Path $Build 'hubmonitor'))
if ($Clean) { $pyInstallerArgs += '--clean' }
Push-Location $Root
try {
    Invoke-Checked -FilePath $Python -Arguments $pyInstallerArgs
} finally {
    Pop-Location
}
if (-not (Test-Path -LiteralPath (Join-Path $Bundle 'HUBMonitor.exe'))) {
    throw 'HUBMonitor.exe nao foi gerado.'
}

Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'install-service.ps1') -Destination $Bundle -Force
New-Item -ItemType Directory -Path (Join-Path $Bundle 'vendor') -Force | Out-Null
# O winsw.exe fica na raiz do bundle: e de la que install-service.ps1
# e o NSIS o procuram. So o WebView2 vai para vendor.
Copy-Item -LiteralPath $WinSwPath -Destination (Join-Path $Bundle 'winsw.exe') -Force
Copy-Item -LiteralPath $WebView2Path -Destination (Join-Path $Bundle 'vendor\MicrosoftEdgeWebView2RuntimeInstallerX64.exe') -Force
Write-Host '    bundle montado'

# ---------------------------------------------------------------------
$SetupPath = Join-Path $Dist 'HUBMonitor-Setup.exe'
if (-not $SkipInstaller) {
    Write-Host ''
    Write-Host '==> NSIS' -ForegroundColor Cyan
    Push-Location (Join-Path $PSScriptRoot 'nsis')
    try {
        # A versao do BUILD-INFO e do instalador tem uma unica origem: -Version.
    Invoke-Checked -FilePath $MakeNsis -Arguments @('/V2', ('/DAPP_VERSION=' + $Version), 'HUBMonitor.nsi')
    } finally {
        Pop-Location
    }
    if (-not (Test-Path -LiteralPath $SetupPath)) { throw 'O instalador nao foi gerado.' }
}

# ---------------------------------------------------------------------
Write-Host ''
Write-Host '==> Resultado' -ForegroundColor Cyan
$info = [ordered]@{
    product    = 'HUB Monitoramento'
    version    = $Version
    built_at   = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK')
    machine    = $env:COMPUTERNAME
    python     = (& $Python --version)
    winsw_sha  = (Get-FileHash -LiteralPath $WinSwPath -Algorithm SHA256).Hash
    webview2_sha = (Get-FileHash -LiteralPath $WebView2Path -Algorithm SHA256).Hash
    # Versoes exatas usadas neste build: permitem reproduzir o ambiente.
    pip_freeze = @(& $Python -m pip freeze 2>$null)
}
if (Test-Path -LiteralPath $SetupPath) {
    $hash = (Get-FileHash -LiteralPath $SetupPath -Algorithm SHA256).Hash
    $size = [math]::Round((Get-Item -LiteralPath $SetupPath).Length / 1MB, 1)
    $info['setup_file'] = 'HUBMonitor-Setup.exe'
    $info['setup_sha256'] = $hash
    $info['setup_size_mb'] = $size
    Write-Host ('    ' + $SetupPath)
    Write-Host ('    SHA-256: ' + $hash)
    Write-Host ('    Tamanho: ' + $size + ' MB')
}
$reportPath = Join-Path $Dist 'BUILD-INFO.json'
$info | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding UTF8
Write-Host ('    Relatorio: ' + $reportPath)
Write-Host ''
Write-Host 'Build concluido.' -ForegroundColor Green
