#Requires -Version 5.1
<#
.SYNOPSIS
    Gera os bundles Windows do agente e do servidor com PyInstaller.

.DESCRIPTION
    O objetivo e que o PDV nao precise de Python instalado, nem de pip,
    nem de internet. O resultado e uma pasta onedir autossuficiente.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\tools\build_windows.ps1

.EXAMPLE
    .\tools\build_windows.ps1 -Target Agent -Clean
#>
[CmdletBinding()]
param(
    [ValidateSet('All', 'Agent', 'Server')][string]$Target = 'All',
    [string]$Python = 'python',
    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $RepoRoot

# Separador de --add-data: ';' no Windows, ':' no macOS/Linux
if ($env:OS -eq 'Windows_NT') { $DataSeparator = ';' } else { $DataSeparator = ':' }
$Sep = [IO.Path]::DirectorySeparatorChar

Write-Host ''
Write-Host '  BERTOLO MONITOR - BUILD DOS BUNDLES' -ForegroundColor Cyan
Write-Host ('  Repositorio: ' + $RepoRoot)
Write-Host ''

function Invoke-PyInstaller {
    param([string[]]$Arguments)
    & $Python -m PyInstaller @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('PyInstaller falhou com codigo ' + $LASTEXITCODE) }
}

function Test-PythonModule {
    param([string]$Module)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Python -c ('import ' + $Module) 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $previous
    }
}

# ---------------------------------------------------------------------
Write-Host '==> Verificando o ambiente de build' -ForegroundColor Cyan
& $Python --version
if ($LASTEXITCODE -ne 0) { throw ('Interpretador Python nao encontrado: ' + $Python) }

if (-not (Test-PythonModule -Module 'PyInstaller')) {
    Write-Host '    PyInstaller ausente. Instalando as dependencias de desenvolvimento...' -ForegroundColor Yellow
    & $Python -m pip install --quiet -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as dependencias.' }
}
Write-Host '    PyInstaller disponivel.' -ForegroundColor Green

$DistDir = Join-Path $RepoRoot 'dist'
$BuildDir = Join-Path $RepoRoot 'build'
$ToolsDir = Join-Path $RepoRoot 'tools'
$CertsDir = Join-Path $RepoRoot 'certs'
New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null

$commonFlags = @('--noconfirm', '--onedir', '--paths', $RepoRoot, '--distpath', $DistDir, '--specpath', $BuildDir)
if ($Clean) { $commonFlags += '--clean' }

# ---------------------------------------------------------------------
if ($Target -eq 'All' -or $Target -eq 'Agent') {
    Write-Host ''
    Write-Host '==> Construindo o agente (BertoloAgent)' -ForegroundColor Cyan
    $agentArgs = $commonFlags + @(
        '--name', 'BertoloAgent',
        '--workpath', (Join-Path $BuildDir 'agent'),
        '--add-data', ((Join-Path $RepoRoot 'certs') + $DataSeparator + 'certs'),
        '--hidden-import', 'psutil',
        '--collect-submodules', 'dns',
        '--collect-submodules', 'psutil',
        (Join-Path $ToolsDir 'entry_agent.py')
    )
    Invoke-PyInstaller -Arguments $agentArgs

    $agentCerts = Join-Path (Join-Path $DistDir 'BertoloAgent') 'certs'
    New-Item -ItemType Directory -Path $agentCerts -Force | Out-Null
    Copy-Item -Path (Join-Path $CertsDir '*') -Destination $agentCerts -Force
    Write-Host '    dist/BertoloAgent pronto.' -ForegroundColor Green
}

# ---------------------------------------------------------------------
if ($Target -eq 'All' -or $Target -eq 'Server') {
    Write-Host ''
    Write-Host '==> Construindo o servidor (BertoloServer)' -ForegroundColor Cyan
    # Caminhos de origem precisam ser absolutos: o PyInstaller os resolve
    # em relacao ao --specpath, nao ao diretorio corrente.
    $dashboardSource = Join-Path (Join-Path $RepoRoot 'server') 'dashboard'
    $dashboardTarget = 'server/dashboard'
    $serverArgs = $commonFlags + @(
        '--name', 'BertoloServer',
        '--workpath', (Join-Path $BuildDir 'server'),
        '--add-data', ($dashboardSource + $DataSeparator + $dashboardTarget),
        '--collect-all', 'uvicorn',
        '--collect-all', 'fastapi',
        '--collect-all', 'librouteros',
        '--collect-all', 'cryptography',
        '--collect-submodules', 'dns',
        '--hidden-import', 'psutil',
        '--hidden-import', 'jinja2',
        (Join-Path $ToolsDir 'entry_server.py')
    )
    Invoke-PyInstaller -Arguments $serverArgs
    Write-Host '    dist/BertoloServer pronto.' -ForegroundColor Green
}

Write-Host ''
Write-Host '==> Concluido' -ForegroundColor Cyan
Get-ChildItem -Path $DistDir -Directory | ForEach-Object { Write-Host ('    ' + $_.FullName) }
Write-Host ''
Write-Host '    Proximo passo: gerar o kit com install/windows/New-OfflineKit.ps1' -ForegroundColor White
