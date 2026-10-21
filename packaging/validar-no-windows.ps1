#Requires -Version 5.1
<#
.SYNOPSIS
    Executa no Windows o ciclo completo: preflight, testes, build, bundle
    e teste HTTPS usando o .exe gerado.

.DESCRIPTION
    Pensa como um "make release" do projeto. Para no primeiro problema e
    imprime o resumo no final. Fora do Windows, apenas mostra o plano.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\packaging\validar-no-windows.ps1
#>
[CmdletBinding()]
param(
    [string]$Version = '1.0.0',
    [string]$Python = 'python',
    [switch]$Plano   # nao executa; so mostra o que seria feito
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$NoWindows = ($env:OS -eq 'Windows_NT')

# O codigo (shared/constants.py) e o VERSION sao fixos. Gerar um instalador
# com outra versao produziria BUILD-INFO dizendo X e software dizendo Y.
$declarada = (Get-Content -LiteralPath (Join-Path $Root 'VERSION') -Raw).Trim()
if ($Version -ne $declarada) {
    Write-Host ('ERRO: -Version ' + $Version + ' difere de VERSION (' + $declarada + ').') -ForegroundColor Red
    Write-Host 'Atualize VERSION, pyproject.toml e shared/constants.py antes de gerar.' -ForegroundColor Yellow
    exit 3
}

function Passo([string]$Titulo) {
    Write-Host ''
    Write-Host ('=== ' + $Titulo + ' ===') -ForegroundColor Cyan
}

function Executar([string]$Rotulo, [string]$Arquivo, [string[]]$Argumentos) {
    Passo $Rotulo
    Write-Host ('  > ' + $Arquivo + ' ' + ($Argumentos -join ' ')) -ForegroundColor DarkGray
    & $Arquivo @Argumentos
    if ($LASTEXITCODE -ne 0) {
        Write-Host ('  FALHOU em: ' + $Rotulo + ' (codigo ' + $LASTEXITCODE + ')') -ForegroundColor Red
        return $false
    }
    return $true
}

$etapas = @(
    @{ Nome = 'Preflight do ambiente'; Arquivo = 'powershell'; Args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $Root 'packaging\preflight-windows.ps1'), '-Python', $Python) },
    @{ Nome = 'Testes automatizados'; Arquivo = $Python; Args = @('-m', 'pytest', 'tests', '-q') },
    @{ Nome = 'Build do instalador'; Arquivo = 'powershell'; Args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $Root 'packaging\build_windows.ps1'), '-Version', $Version, '-Python', $Python) },
    @{ Nome = 'Bundle congelado'; Arquivo = $Python; Args = @((Join-Path $Root 'tools\smoke_bundle.py'), (Join-Path $Root 'dist\HUBMonitor')) },
    @{ Nome = 'HTTPS com o .exe gerado'; Arquivo = $Python; Args = @((Join-Path $Root 'tools\e2e_https_test.py'), '--exe', (Join-Path $Root 'dist\HUBMonitor\HUBMonitor.exe'), '--port', '8453', '--health-port', '8013') }
)

if (-not $NoWindows -or $Plano) {
    Write-Host ''
    Write-Host 'PLANO DE VALIDACAO NO WINDOWS' -ForegroundColor Cyan
    Write-Host ('Raiz: ' + $Root)
    foreach ($etapa in $etapas) {
        Write-Host ('  - ' + $etapa.Nome)
        Write-Host ('      ' + $etapa.Arquivo + ' ' + ($etapa.Args -join ' ')) -ForegroundColor DarkGray
    }
    Write-Host ''
    if (-not $NoWindows) {
        Write-Host 'Este ambiente nao e Windows: nada foi executado.' -ForegroundColor Yellow
        exit 2
    }
    exit 0
}

$falhas = @()
foreach ($etapa in $etapas) {
    if (-not (Executar $etapa.Nome $etapa.Arquivo $etapa.Args)) {
        $falhas += $etapa.Nome
        break
    }
}

Passo 'Resultado'
$exe = Join-Path $Root 'dist\HUBMonitor-Setup.exe'
$info = Join-Path $Root 'dist\BUILD-INFO.json'
if ($falhas.Count -eq 0 -and (Test-Path -LiteralPath $exe)) {
    $hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
    $tamanho = [math]::Round((Get-Item -LiteralPath $exe).Length / 1MB, 1)
    Write-Host ('  INSTALADOR: ' + $exe)
    Write-Host ('  Tamanho   : ' + $tamanho + ' MB')
    Write-Host ('  SHA-256   : ' + $hash)
    if (Test-Path -LiteralPath $info) {
        Write-Host ('  BUILD-INFO: ' + $info)
    }
    Write-Host '  Tudo verificado. Instale em uma maquina limpa.' -ForegroundColor Green
    exit 0
}

Write-Host '  Validacao incompleta.' -ForegroundColor Red
foreach ($item in $falhas) { Write-Host ('  - falhou: ' + $item) -ForegroundColor Red }
if (-not (Test-Path -LiteralPath $exe)) {
    Write-Host '  - dist\HUBMonitor-Setup.exe nao foi gerado' -ForegroundColor Red
}
exit 1
