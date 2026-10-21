#Requires -Version 5.1
<#
    Instala, remove e configura o servico do HUB Monitoramento.

    Chamado pelo instalador NSIS. Uma instalacao limpa precisa de mais do
    que copiar arquivos: o servidor exige credencial de agente, certificado
    TLS proprio, porta consistente e pastas de dados proteginas. Tudo isso
    e criado aqui, de forma idempotente:

      - .env persistente em $InstallDir e preservado em reinstalacoes;
      - credencial do agente gerada uma vez e mantida;
      - CA + certificado do servidor gerados so quando faltam (trocar a CA
        invalidaria os arquivos .hubconn ja distribuidos);
      - CA publica importada no repositorio de raizes do Windows, para que
        navegador e WebView2 aceitem https://127.0.0.1;
      - .env e chave privada com ACL restrita (SYSTEM + Administradores);
      - firewall na mesma porta configurada;
      - health check obrigatorio antes de declarar sucesso.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('server', 'agent')][string]$Mode,
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [int]$Port = 8443,
    [string]$StoreName = 'HUB Monitoramento',
    [string]$MachineName = '',
    [string]$LocalSubnet = '192.168.0.0/24',
    [string]$LanIp = '',
    [ValidateSet('install', 'remove', 'import-connection')][string]$Action = 'install',
    [string]$ConnectionFile = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ServiceName = if ($Mode -eq 'server') { 'HUBMonitorServer' } else { 'HUBMonitorAgent' }
$OtherName = if ($Mode -eq 'server') { 'HUBMonitorAgent' } else { 'HUBMonitorServer' }
$DisplayName = if ($Mode -eq 'server') {
    'HUB Monitoramento - Servidor da loja'
} else {
    'HUB Monitoramento - Computador monitorado'
}
$Exe = Join-Path $InstallDir 'HUBMonitor.exe'
$WinSw = Join-Path $InstallDir 'winsw.exe'
$Wrapper = Join-Path $InstallDir ($ServiceName.ToLowerInvariant() + '.exe')
$WrapperXml = Join-Path $InstallDir ($ServiceName.ToLowerInvariant() + '.xml')
$EnvFile = Join-Path $InstallDir '.env'
$DataRoot = Join-Path $env:ProgramData 'HUBMonitor'
$DataDir = Join-Path $DataRoot 'data'
$LogDir = Join-Path $DataRoot 'logs'
$ConfigBackup = Join-Path $DataRoot 'config-backup.env'
$CertDir = Join-Path $DataRoot 'certs'
$CaFile = Join-Path $CertDir 'server-ca.pem'
$ServerCert = Join-Path $CertDir 'server.pem'
$ServerKey = Join-Path $CertDir 'server-key.pem'
$ConnectionPath = Join-Path $DataRoot 'connection.json'

function Say([string]$Message) { Write-Host ('    ' + $Message) }
function Fail([string]$Message, [int]$Code = 10) {
    Write-Host ('    [X] ' + $Message) -ForegroundColor Red
    exit $Code
}

function Restrict-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    & icacls $Path /inheritance:r /grant:r '*S-1-5-18:F' '*S-1-5-32-544:F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw ('Falha ao restringir ACL de ' + $Path) }
}

function Restrict-Dir([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    & icacls $Path /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw ('Falha ao restringir ACL de ' + $Path) }
}

function Restore-ConfigBackup {
    # Sobrevive a uma desinstalacao: sem isso, a credencial do agente e os
    # ajustes da loja sumiriam e todos os .hubconn distribuidos parariam.
    if ((-not (Test-Path -LiteralPath $EnvFile)) -and (Test-Path -LiteralPath $ConfigBackup)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
        Copy-Item -LiteralPath $ConfigBackup -Destination $EnvFile -Force
        Say 'Configuracao anterior recuperada da desinstalacao.'
    }
}

function Read-EnvMap {
    $map = @{}
    if (-not (Test-Path -LiteralPath $EnvFile)) { return $map }
    foreach ($line in (Get-Content -LiteralPath $EnvFile -Encoding UTF8)) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith('#')) { continue }
        $index = $trimmed.IndexOf('=')
        if ($index -lt 1) { continue }
        $map[$trimmed.Substring(0, $index).Trim()] = $trimmed.Substring($index + 1).Trim()
    }
    return $map
}

function Write-EnvMap([hashtable]$Map) {
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add('# Gerado pelo instalador do HUB Monitoramento.')
    $lines.Add('# Editar pela pagina de Configuracoes ou reexecutar o instalador.')
    foreach ($key in ($Map.Keys | Sort-Object)) {
        $lines.Add($key + '=' + $Map[$key])
    }
    $text = ($lines -join [Environment]::NewLine) + [Environment]::NewLine
    # UTF-8 sem BOM: BOM corromperia a primeira chave lida pelo Python.
    [System.IO.File]::WriteAllText($EnvFile, $text, (New-Object System.Text.UTF8Encoding($false)))
    Restrict-File $EnvFile
}

function New-AgentToken {
    return ([guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N'))
}

function Get-LanIp {
    try {
        $socket = New-Object System.Net.Sockets.UdpClient
        $socket.Connect('1.1.1.1', 53)
        $ip = $socket.Client.LocalEndPoint.Address.ToString()
        $socket.Close()
        if ($ip -and $ip -notlike '127.*') { return $ip }
    } catch {
        # sem rota: cai no fallback abaixo
    }
    try {
        $address = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
            Select-Object -First 1
        if ($address) { return $address.IPAddress }
    } catch {
        # irrelevante
    }
    return '127.0.0.1'
}

function Invoke-Native([string]$FilePath, [string[]]$Arguments = @()) {
    # Com ErrorActionPreference=Stop, um executavel que escreve em stderr
    # pode virar NativeCommandError antes de lermos $LASTEXITCODE.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $code = 0
    try {
        $output = & $FilePath @Arguments 2>&1
        if ($null -ne $LASTEXITCODE) { $code = $LASTEXITCODE }
    } finally {
        $ErrorActionPreference = $previous
    }
    return [pscustomobject]@{
        ExitCode = $code
        Output   = ([string]($output | Out-String)).Trim()
    }
}

function Stop-And-Delete([string]$Name) {
    $service = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $service) { return }
    Invoke-Native 'sc.exe' @('stop', $Name) | Out-Null
    Start-Sleep -Seconds 2
    Invoke-Native 'sc.exe' @('delete', $Name) | Out-Null
    Start-Sleep -Seconds 1
}

function Remove-HubCaCertificate {
    # Limpeza nao pode impedir a desinstalacao: qualquer falha e ignorada.
    try {
        $certs = Get-ChildItem -Path 'Cert:\LocalMachine\Root' -ErrorAction SilentlyContinue |
            Where-Object { $_.Subject -like '*HUB Monitoramento Local CA*' }
        foreach ($cert in $certs) {
            Remove-Item -LiteralPath ('Cert:\LocalMachine\Root\' + $cert.Thumbprint) -Force -ErrorAction SilentlyContinue
        }
    } catch {
        Say ('Aviso: nao foi possivel limpar a CA do repositorio. ' + $_.Exception.Message)
    }
}

function Register-HubService {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][ValidateSet('server', 'agent')][string]$TargetMode)

    $svcName = if ($TargetMode -eq 'server') { 'HUBMonitorServer' } else { 'HUBMonitorAgent' }
    $svcDisplay = if ($TargetMode -eq 'server') {
        'HUB Monitoramento - Servidor da loja'
    } else {
        'HUB Monitoramento - Computador monitorado'
    }
    $wrapper = Join-Path $InstallDir ($svcName.ToLowerInvariant() + '.exe')
    $wrapperXml = Join-Path $InstallDir ($svcName.ToLowerInvariant() + '.xml')

    if (-not (Test-Path -LiteralPath $Exe)) { Fail ('Executavel ausente: ' + $Exe) 10 }
    if (-not (Test-Path -LiteralPath $WinSw)) { Fail ('winsw.exe ausente: ' + $WinSw) 11 }

    $xml = @"
<service>
  <id>$svcName</id>
  <name>$svcDisplay</name>
  <description>HUB Monitoramento - coleta continua de conectividade.</description>
  <executable>$Exe</executable>
  <arguments>$TargetMode</arguments>
  <workingdirectory>$InstallDir</workingdirectory>
  <logpath>$LogDir</logpath>
  <log mode="roll-by-size">
    <sizeThreshold>10485760</sizeThreshold>
    <keepFiles>5</keepFiles>
  </log>
  <onfailure action="restart" delay="30 sec"/>
  <startmode>Automatic</startmode>
  <stoptimeout>20 sec</stoptimeout>
</service>
"@
    [System.IO.File]::WriteAllText($wrapperXml, $xml, (New-Object System.Text.UTF8Encoding($false)))

    Stop-And-Delete $svcName
    Copy-Item -LiteralPath $WinSw -Destination $wrapper -Force
    $installed = Invoke-Native $wrapper @('install')
    if ($installed.ExitCode -ne 0) {
        Say ('winsw install: ' + $installed.Output)
        Fail 'Falha ao registrar o servico (winsw install).' 60
    }
    Invoke-Native 'sc.exe' @('failure', $svcName, 'reset=', '86400', 'actions=', 'restart/30000/restart/30000/restart/30000') | Out-Null
    Invoke-Native 'sc.exe' @('config', $svcName, 'start=', 'auto') | Out-Null
    $started = Invoke-Native $wrapper @('start')
    if ($started.ExitCode -ne 0) {
        Say ('winsw start: ' + $started.Output)
        Fail 'Falha ao iniciar o servico (winsw start).' 60
    }
}


function Get-PayloadField($Object, [string]$Name) {
    # StrictMode lanca ao acessar propriedade inexistente. Uma versao
    # diferente do servico nao pode derrubar o instalador no fim.
    if ($null -eq $Object) { return '' }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return '' }
    return [string]$property.Value
}

function Wait-ServerHealth([int]$TimeoutSeconds = 90) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $previous = [Net.ServicePointManager]::ServerCertificateValidationCallback
    # A sonda e local (127.0.0.1) e o certificado e o nosso proprio.
    [Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
    try {
        $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
        while ((Get-Date) -lt $deadline) {
            try {
                $response = Invoke-RestMethod -Uri ('https://127.0.0.1:' + $Port + '/health') -TimeoutSec 5 -ErrorAction Stop
                if ($response.status -eq 'ok') { return $response }
            } catch {
                Start-Sleep -Seconds 2
            }
        }
    } finally {
        [Net.ServicePointManager]::ServerCertificateValidationCallback = $previous
    }
    return $null
}

function Test-PortFree([int]$Port) {
    # Tenta abrir a porta. Se outro programa a ocupa, o instalador precisa
    # dizer isso com clareza em vez de falhar no health check.
    $listener = $null
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Any, $Port)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($null -ne $listener) {
            try { $listener.Stop() } catch { }
        }
    }
}

function Register-BackupTask {
    # O comando correto e "server --backup": o entry point despacha o
    # primeiro argumento como comando. "--backup" sozinho nao funcionaria.
    $action = New-ScheduledTaskAction -Execute $Exe -Argument 'server --backup' -WorkingDirectory $InstallDir
    $trigger = New-ScheduledTaskTrigger -Daily -At '03:00'
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    Register-ScheduledTask -TaskName 'HUBMonitorBackup' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Say 'Backup diario agendado (03:00).'
}

function Unregister-BackupTask {
    try {
        Unregister-ScheduledTask -TaskName 'HUBMonitorBackup' -Confirm:$false -ErrorAction Stop
        Say 'Tarefa de backup removida.'
    } catch {
        # Nao existir e o caso normal em maquinas sem instalacao previa.
    }
}

function Wait-AgentHealth([int]$TimeoutSeconds = 60) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri 'http://127.0.0.1:8010/health' -TimeoutSec 4 -ErrorAction Stop
            if ($response.status -eq 'ok') { return $response }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    return $null
}

function Write-RoleFile([string]$ApiUrl) {
    $role = [ordered]@{
        mode = $Mode
        api_url = $ApiUrl
        install_dir = $InstallDir
        service_name = $ServiceName
        store_name = $StoreName
    }
    if ($Mode -eq 'server') { $role['ca_file'] = $CaFile }
    $text = ($role | ConvertTo-Json)
    [System.IO.File]::WriteAllText(
        (Join-Path $DataRoot 'role.json'),
        $text,
        (New-Object System.Text.UTF8Encoding($false))
    )
    Restrict-File (Join-Path $DataRoot 'role.json')
}

# =====================================================================
if ($Action -eq 'remove') {
    Stop-And-Delete $ServiceName
    Stop-And-Delete $OtherName
    Get-NetFirewallRule -DisplayName 'HUB Monitoramento API' -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction SilentlyContinue
    Unregister-BackupTask
    Remove-HubCaCertificate
    Say 'Servicos, regra de firewall, CA e backup removidos. Dados preservados.'
    exit 0
}

if (-not (Test-Path -LiteralPath $Exe)) { Fail ('Executavel ausente: ' + $Exe) 10 }
foreach ($dir in @($DataRoot, $DataDir, $LogDir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

if ($Action -eq 'import-connection') {
    if (-not $ConnectionFile -or -not (Test-Path -LiteralPath $ConnectionFile)) {
        Fail 'Arquivo de conexao nao informado ou inexistente.' 30
    }
    Copy-Item -LiteralPath $ConnectionFile -Destination $ConnectionPath -Force
    Restrict-File $ConnectionPath
    $service = Get-Service -Name 'HUBMonitorAgent' -ErrorAction SilentlyContinue
    if ($service) {
        Restart-Service -Name 'HUBMonitorAgent' -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
    Say ('Arquivo de conexao importado em ' + $ConnectionPath)
    exit 0
}

Restore-ConfigBackup
$envMap = Read-EnvMap

if ($Mode -eq 'server') {
    # Porta ocupada por terceiros: falha cedo e com instrucao clara, em vez
    # de esperar o health check e dizer "API nao respondeu".
    Stop-And-Delete 'HUBMonitorServer'
    if (-not (Test-PortFree $Port)) {
        Fail ('A porta ' + $Port + ' ja esta em uso por outro programa. Volte e escolha outra porta.') 72
    }

    # Dados e logs contem nomes de caixas, IPs e mensagens de erro: nao
    # podem ficar legiveis por qualquer usuario da maquina. Criados aqui
    # (e nao pelo servico) para que ja nasçam com a ACL restrita.
    foreach ($pasta in @($DataDir, $LogDir)) {
        New-Item -ItemType Directory -Path $pasta -Force | Out-Null
        Restrict-Dir $pasta
    }

    New-Item -ItemType Directory -Path $CertDir -Force | Out-Null

    # O instalador pode corrigir o endereco detectado (opcoes avancadas).
    if ($LanIp) {
        $lanIp = $LanIp
        Say ('Endereco informado manualmente: ' + $lanIp)
    } else {
        $lanIp = Get-LanIp
        Say ('Endereco detectado automaticamente: ' + $lanIp)
    }

    # Certificado: so gera se faltar. Trocar a CA invalidaria os .hubconn.
    if (-not ((Test-Path -LiteralPath $ServerCert) -and (Test-Path -LiteralPath $ServerKey) -and (Test-Path -LiteralPath $CaFile))) {
        Say 'Gerando certificado TLS local...'
        & $Exe server --generate-tls-cert --tls-dir $CertDir --server-name $env:COMPUTERNAME --server-ip $lanIp | Out-Null
        if ($LASTEXITCODE -ne 0) { Fail 'Falha ao gerar o certificado TLS.' 20 }
        if (-not ((Test-Path -LiteralPath $ServerCert) -and (Test-Path -LiteralPath $ServerKey) -and (Test-Path -LiteralPath $CaFile))) {
            Fail 'Certificado TLS nao foi criado.' 20
        }
    } else {
        Say 'Certificado TLS existente preservado.'
    }

    Restrict-Dir $CertDir
    Restrict-File $ServerKey
    Restrict-File $ServerCert
    Restrict-File $CaFile

    # A CA publica vai para o repositorio de raizes: navegador e WebView2
    # passam a aceitar https://127.0.0.1 sem aviso.
    try {
        $existing = Get-ChildItem -Path 'Cert:\LocalMachine\Root' -ErrorAction SilentlyContinue |
            Where-Object { $_.Subject -like '*HUB Monitoramento Local CA*' }
        if (-not $existing) {
            $base64 = ((Get-Content -LiteralPath $CaFile) | Where-Object { $_ -notmatch '-----' }) -join ''
            $cerPath = Join-Path $CertDir 'server-ca.cer'
            [System.IO.File]::WriteAllBytes($cerPath, [Convert]::FromBase64String($base64))
            Import-Certificate -FilePath $cerPath -CertStoreLocation 'Cert:\LocalMachine\Root' | Out-Null
            Restrict-File $cerPath
            Say 'CA publica instalada no repositorio de raizes do Windows.'
        }
    } catch {
        Say ('Aviso: nao foi possivel instalar a CA no repositorio. ' + $_.Exception.Message)
    }

    if (-not $envMap.ContainsKey('AGENT_INGEST_TOKEN') -or -not $envMap['AGENT_INGEST_TOKEN']) {
        $envMap['AGENT_INGEST_TOKEN'] = New-AgentToken
        Say 'Credencial do agente gerada.'
    } else {
        Say 'Credencial do agente preservada.'
    }

    $envMap['STORE_NAME'] = $StoreName
    $envMap['SERVER_HOST'] = '0.0.0.0'
    $envMap['SERVER_PORT'] = [string]$Port
    $envMap['SERVER_ALLOW_HTTP'] = 'false'
    $envMap['SERVER_TLS_CERT_FILE'] = $ServerCert
    $envMap['SERVER_TLS_KEY_FILE'] = $ServerKey
    $envMap['LOCAL_SUBNET'] = $LocalSubnet
    $envMap['DATA_DIR'] = $DataDir
    $envMap['LOG_DIR'] = $LogDir
    $envMap['DB_PATH'] = (Join-Path $DataDir 'bertolo_monitor.db')
    # O servidor tambem e um computador monitorado: o agente roda aqui.
    $envMap['MACHINE_NAME'] = $env:COMPUTERNAME
    $envMap['CONNECTION_FILE'] = (Join-Path $DataRoot 'server-connection.json')
    Write-EnvMap $envMap

    Get-NetFirewallRule -DisplayName 'HUB Monitoramento API' -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName 'HUB Monitoramento API' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -RemoteAddress $LocalSubnet -Profile Any | Out-Null

    Register-HubService -TargetMode 'server'
    Write-RoleFile ('https://127.0.0.1:' + $Port)

    Say 'Aguardando a API responder...'
    $health = Wait-ServerHealth -TimeoutSeconds 90
    if (-not $health) {
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        $state = 'ausente'
        if ($service) { $state = [string]$service.Status }
        Invoke-Native $Wrapper @('stop') | Out-Null
        $logFile = Join-Path $LogDir 'server.log'
        if (Test-Path -LiteralPath $logFile) {
            Say 'Ultimas linhas do log:'
            Get-Content -LiteralPath $logFile -Tail 15 | ForEach-Object { Write-Host ('      ' + $_) }
        }
        Fail ('A API nao respondeu na porta ' + $Port + ' (servico: ' + $state + ').') 70
    }

    Say ('API respondendo: versao ' + (Get-PayloadField $health 'version') + ', banco ' + (Get-PayloadField $health 'database'))

    # O pedido exige que o servidor monitore a propria conectividade.
    # O agente roda nesta maquina apontando para a API local; o arquivo
    # de conexao e gerado pelo proprio executavel (fingerprint correto).
    try {
        $selfConnection = Join-Path $DataRoot 'server-connection.json'
        & $Exe export-connection --path $selfConnection --public-url ('https://127.0.0.1:' + $Port) | Out-Null
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $selfConnection)) {
            throw ('export-connection retornou ' + $LASTEXITCODE)
        }
        Restrict-File $selfConnection
        Register-HubService -TargetMode 'agent'
        Say 'Monitoramento da propria maquina ativo.'
    } catch {
        Say ('Aviso: nao foi possivel monitorar a propria maquina. ' + $_.Exception.Message)
    }

    # Só agenda o backup depois de a API responder: nao faz sentido
    # agendar manutencao para uma instalacao quebrada.
    try {
        Register-BackupTask
    } catch {
        Say ('Aviso: nao foi possivel agendar o backup diario. ' + $_.Exception.Message)
    }

    Say ('Endereco da loja: https://' + $lanIp + ':' + $Port)
    exit 0
}

# ------------------------------- agente -------------------------------
if (-not $envMap.ContainsKey('CONNECTION_FILE')) {
    $envMap['CONNECTION_FILE'] = $ConnectionPath
}
if ($MachineName) { $envMap['MACHINE_NAME'] = $MachineName }
$envMap['DATA_DIR'] = $DataDir
$envMap['LOG_DIR'] = $LogDir
Write-EnvMap $envMap

# No PDV vale a mesma regra: dados e logs nao ficam legiveis por qualquer
# usuario da maquina.
foreach ($pasta in @($DataDir, $LogDir)) {
    New-Item -ItemType Directory -Path $pasta -Force | Out-Null
    Restrict-Dir $pasta
}

if (-not (Test-Path -LiteralPath $ConnectionPath)) {
    Say 'Aviso: ainda sem arquivo de conexao. Importe o .hubconn pela janela do HUB Monitoramento.'
}

# Uma maquina monitorada nao hospeda o servidor da loja.
Stop-And-Delete 'HUBMonitorServer'
Register-HubService -TargetMode 'agent'
Write-RoleFile 'http://127.0.0.1:8010'

Say 'Aguardando o agente responder...'
$health = Wait-AgentHealth -TimeoutSeconds 60
if (-not $health) {
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    $state = 'ausente'
    if ($service) { $state = [string]$service.Status }
    Invoke-Native $Wrapper @('stop') | Out-Null
    $logFile = Join-Path $LogDir 'agent.log'
    if (Test-Path -LiteralPath $logFile) {
        Say 'Ultimas linhas do log:'
        Get-Content -LiteralPath $logFile -Tail 15 | ForEach-Object { Write-Host ('      ' + $_) }
    }
    Fail ('O agente nao respondeu (estado do servico: ' + $state + ').') 70
}

Say ('Agente respondendo: maquina ' + (Get-PayloadField $health 'machine_name'))
if (-not (Test-Path -LiteralPath $ConnectionPath)) {
    Say 'Importe o arquivo .hubconn pela janela para comecar a enviar dados.'
}
exit 0
