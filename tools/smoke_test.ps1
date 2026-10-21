#Requires -Version 5.1
<#
.SYNOPSIS
    Valida uma instalacao do Bertolo Monitor ja existente.

.DESCRIPTION
    Verificacoes somente leitura:
      - servico/tarefa registrado e em execucao;
      - health local do agente respondendo;
      - fila local do agente;
      - API central respondendo e recebendo dados deste caixa.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\tools\smoke_test.ps1 -KitPath C:\BertoloKit
#>
[CmdletBinding()]
param(
    [string]$KitPath = $PSScriptRoot,
    [ValidateSet('Agent', 'Server', 'Both')][string]$Component = 'Both',
    [string]$ServerUrl = 'http://127.0.0.1:8000',
    [int]$HealthPort = 8010
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

if (Test-Path -LiteralPath (Join-Path $KitPath 'lib\Common.ps1')) {
    . (Join-Path $KitPath 'lib\Common.ps1')
}
if (Test-Path -LiteralPath (Join-Path $KitPath 'lib\Service.ps1')) {
    . (Join-Path $KitPath 'lib\Service.ps1')
}

$failures = 0
function Report {
    param([string]$Label, [bool]$Ok, [string]$Detail = '')
    if ($Ok) { Write-Host ('  [PASS] ' + $Label) -ForegroundColor Green }
    else { Write-Host ('  [FAIL] ' + $Label + ' ' + $Detail) -ForegroundColor Red; $script:failures++ }
}

Write-Host ''
Write-Host '  BERTOLO MONITOR - SMOKE TEST' -ForegroundColor Cyan
Write-Host ''

if ($Component -eq 'Agent' -or $Component -eq 'Both') {
    Write-Host 'Agente:' -ForegroundColor White
    $state = Get-BertoloServiceState -ServiceName 'BertoloAgent'
    Report -Label 'servico/tarefa BertoloAgent registrado' -Ok $state.Exists -Detail $state.State

    try {
        $health = Invoke-RestMethod -Uri ('http://127.0.0.1:' + $HealthPort + '/health') -TimeoutSec 5 -ErrorAction Stop
        Report -Label 'health local respondendo' -Ok ($health.status -eq 'ok') -Detail ([string]$health.status)
        Write-Host ('         maquina=' + $health.machine_name + ' versao=' + $health.agent_version)
        if ($health.queue) {
            Write-Host ('         fila: ' + [string]$health.queue.total + ' pendente(s), ' + [string]$health.queue.sent_total + ' enviado(s)')
        }
        $offline = @()
        if ($health.monitors) {
            foreach ($name in $health.monitors.PSObject.Properties.Name) {
                $monitor = $health.monitors.$name
                if ($monitor.ok -eq $false) { $offline += $name }
            }
        }
        if ($offline.Count -gt 0) {
            Write-Host ('         monitores em falha: ' + ($offline -join ', ')) -ForegroundColor Yellow
        } else {
            Write-Host '         nenhum monitor em falha' -ForegroundColor Green
        }
    } catch {
        Report -Label 'health local respondendo' -Ok $false -Detail $_.Exception.Message
    }
    Write-Host ''
}

if ($Component -eq 'Server' -or $Component -eq 'Both') {
    Write-Host 'Servidor:' -ForegroundColor White
    $state = Get-BertoloServiceState -ServiceName 'BertoloServer'
    Report -Label 'servico/tarefa BertoloServer registrado' -Ok $state.Exists -Detail $state.State

    try {
        $health = Invoke-RestMethod -Uri ($ServerUrl.TrimEnd('/') + '/health') -TimeoutSec 5 -ErrorAction Stop
        Report -Label 'API respondendo em /health' -Ok ($health.status -eq 'ok')
        Write-Host ('         versao=' + $health.version + ' maquinas=' + [string]$health.machines + ' medicoes=' + [string]$health.measurements)
        Write-Host ('         incidentes abertos=' + [string]$health.open_incidents)
        if ($health.mikrotik_enabled) { Write-Host ('         mikrotik_ok=' + [string]$health.mikrotik_ok) }

        try {
            $status = Invoke-RestMethod -Uri ($ServerUrl.TrimEnd('/') + '/api/v1/status') -TimeoutSec 8 -ErrorAction Stop
            foreach ($machine in $status.machines) {
                $flag = 'OFFLINE'
                if ($machine.online) { $flag = 'online' }
                Write-Host ('         ' + $machine.machine_name.PadRight(10) + $flag + '  diag=' + [string]$machine.diagnosis)
            }
            if (-not $status.machines) { Write-Host '         nenhum caixa reportou ainda' -ForegroundColor Yellow }
        } catch {
            Report -Label 'consulta de /api/v1/status' -Ok $false -Detail $_.Exception.Message
        }
    } catch {
        Report -Label 'API respondendo em /health' -Ok $false -Detail $_.Exception.Message
    }
    Write-Host ''
}

if ($failures -gt 0) {
    Write-Host ('RESULTADO: ' + $failures + ' verificacao(oes) com falha.') -ForegroundColor Red
    exit 1
}
Write-Host 'RESULTADO: instalacao saudavel.' -ForegroundColor Green
exit 0
