#Requires -Version 5.1
<#
.SYNOPSIS
    Descobre o emissor de NFC-e no CAIXA02 sem abrir arquivos de log.
.DESCRIPTION
    Le apenas metadados de programas instalados, processos, servicos e arquivos
    candidatos. Nunca le conteudo de log, XML ou documento fiscal.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'SilentlyContinue'
$pattern = '(?i)nfc-e|nfce|nfe|fiscal|sefaz|sat|pdv|caixa'

Write-Host 'BERTOLO MONITOR - descoberta somente leitura do emissor NFC-e'
Write-Host ('Maquina: ' + $env:COMPUTERNAME)
Write-Host 'Nenhum conteudo de log ou arquivo fiscal sera aberto.'

$uninstallRoots = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$applications = @(
    foreach ($root in $uninstallRoots) {
        Get-ItemProperty -Path $root |
            Where-Object { $_.DisplayName -and ($_.DisplayName -match $pattern -or $_.Publisher -match $pattern) } |
            Select-Object @{Name='Name';Expression={$_.DisplayName}},
                @{Name='Publisher';Expression={$_.Publisher}},
                @{Name='Version';Expression={$_.DisplayVersion}},
                @{Name='InstallLocation';Expression={$_.InstallLocation}}
    }
) | Sort-Object Name, InstallLocation -Unique

Write-Host "`nPROGRAMAS INSTALADOS (nome, fabricante, versao e pasta)"
if ($applications.Count) { $applications | Format-Table -AutoSize | Out-String -Width 240 | Write-Host }
else { Write-Host 'Nenhum nome de programa correspondente encontrado.' }

$processes = @(
    Get-Process | ForEach-Object {
        $path = ''
        try { $path = $_.Path } catch { }
        if ($_.ProcessName -match $pattern -or $path -match $pattern) {
            [pscustomobject]@{ Name = $_.ProcessName; Id = $_.Id; Executable = $path }
        }
    }
)
Write-Host "`nPROCESSOS ATIVOS COM NOME/PATH RELACIONADO"
if ($processes.Count) { $processes | Format-Table -AutoSize | Out-String -Width 240 | Write-Host }
else { Write-Host 'Nenhum processo correspondente encontrado.' }

$services = @(Get-CimInstance Win32_Service | Where-Object { $_.Name -match $pattern -or $_.DisplayName -match $pattern } |
    Select-Object Name, DisplayName, State, StartMode)
Write-Host "`nSERVICOS RELACIONADOS"
if ($services.Count) { $services | Format-Table -AutoSize | Out-String -Width 240 | Write-Host }
else { Write-Host 'Nenhum servico correspondente encontrado.' }

$roots = @($applications.InstallLocation | Where-Object { $_ -and (Test-Path -LiteralPath $_) })
$roots += @($processes.Executable | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | ForEach-Object { Split-Path -Parent $_ })
$roots = @($roots | Sort-Object -Unique)
$seen = @{}
$candidates = @(
    foreach ($root in $roots) {
        Get-ChildItem -LiteralPath $root -File -Recurse -Depth 5 -Include *.log,*.txt -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '(?i)log|trace|nfc|nfe|fiscal|sefaz|sat' } |
            ForEach-Object {
                if (-not $seen.ContainsKey($_.FullName)) {
                    $seen[$_.FullName] = $true
                    [pscustomobject]@{
                        Name = $_.Name
                        Path = $_.FullName
                        SizeBytes = $_.Length
                        LastWriteTime = $_.LastWriteTime
                    }
                }
            }
    }
) | Select-Object -First 100

Write-Host "`nARQUIVOS CANDIDATOS (somente metadados; conteudo nao lido)"
if ($candidates.Count) { $candidates | Format-Table -AutoSize | Out-String -Width 260 | Write-Host }
else { Write-Host 'Nenhum arquivo candidato encontrado nas pastas identificadas.' }

Write-Host "`nEnvie este resultado para identificar o emissor e escolher um log adequado."
