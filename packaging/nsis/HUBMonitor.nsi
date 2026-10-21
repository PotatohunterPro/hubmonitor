; Instalador do HUB Monitoramento para Windows.
; Gera HUBMonitor-Setup.exe com dois modos: servidor da loja e
; computador monitorado.
;
; Executado por packaging/build_windows.ps1, que roda makensis com o
; diretorio de trabalho em packaging/nsis. Todo caminho de origem e
; relativo a packaging/nsis (..\..\dist).
;
; Requer NSIS 3.x e "..\..\dist\HUBMonitor" ja gerado pelo PyInstaller.

Unicode true
!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

!define APP_NAME "HUB Monitoramento"
; A versao vem do build (-Version). 1.0.0 e apenas o padrao.
!ifndef APP_VERSION
  !define APP_VERSION "1.0.0"
!endif
!define APP_PUBLISHER "HUB"
!define APP_EXE "HUBMonitor.exe"
!define BUNDLE_DIR "..\..\dist\HUBMonitor"
!define REG_UNINSTALL "Software\Microsoft\Windows\CurrentVersion\Uninstall\HUBMonitoramento"
!define REG_APP "Software\HUB\HUBMonitoramento"
!define WEBVIEW2_KEY "SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\${F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
!define WEBVIEW2_INSTALLER "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"

Name "${APP_NAME}"
BrandingText "${APP_NAME} ${APP_VERSION}"
OutFile "..\..\dist\HUBMonitor-Setup.exe"
InstallDir "$PROGRAMFILES64\HUB Monitoramento"
InstallDirRegKey HKLM "${REG_APP}" "InstallDir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "CompanyName" "${APP_PUBLISHER}"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "LegalCopyright" "${APP_PUBLISHER}"

!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "HUB Monitoramento"
!define MUI_WELCOMEPAGE_TEXT "Este assistente instala o HUB Monitoramento.\r\n\r\nVoce vai escolher se este computador e o servidor da loja ou um computador monitorado. Nenhum comando precisa ser digitado."
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_PARAMETERS "ui"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir o HUB Monitoramento"
!define MUI_FINISHPAGE_TEXT "O servico foi instalado e esta em execucao.$$
$$
No SERVIDOR, a pagina de configuracao abre no navegador: crie a senha administrativa, informe o token do bot e o grupo do Telegram (com teste antes de salvar) e escolha a UF e o documento fiscal. Depois clique em Exportar conexao (.hubconn).$$
$$
Nos COMPUTADORES MONITORADOS, importe o arquivo .hubconn pela janela do agente."

!insertmacro MUI_PAGE_WELCOME
Page custom ModePageCreate ModePageLeave
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

Var Mode
Var StoreName
Var MachineName
Var Port
Var LocalSubnet
Var ModeServerRadio
Var ModeAgentRadio
Var StoreNameField
Var MachineNameField
Var PortField
Var LanIp
Var LanIpField
Var SubnetField
Var Dialog

Function .onInit
  StrCpy $Mode "server"
  StrCpy $StoreName "Mercado Bertolo"
  StrCpy $Port "8443"
  StrCpy $LocalSubnet "192.168.0.0/24"
  StrCpy $LanIp ""
  ReadEnvStr $MachineName "COMPUTERNAME"
FunctionEnd

Function ModePageCreate
  !insertmacro MUI_HEADER_TEXT "Modo de instalacao" "Escolha o papel deste computador na loja."
  nsDialogs::Create 1018
  Pop $Dialog
  ${If} $Dialog == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 0 100% 24u "O servidor recebe os dados, guarda o historico e envia mensagens ao Telegram. O computador monitorado apenas verifica a propria conexao e envia ao servidor."
  Pop $0

  ${NSD_CreateRadioButton} 0 32u 100% 12u "Servidor da loja (um por loja)"
  Pop $ModeServerRadio
  ${NSD_CreateRadioButton} 0 50u 100% 12u "Computador monitorado (um por caixa)"
  Pop $ModeAgentRadio

  ${If} $Mode == "server"
    ${NSD_SetState} $ModeServerRadio ${BST_CHECKED}
  ${Else}
    ${NSD_SetState} $ModeAgentRadio ${BST_CHECKED}
  ${EndIf}

  ${NSD_CreateLabel} 0 80u 100% 10u "Nome da loja (aparece nas mensagens):"
  Pop $0
  ${NSD_CreateText} 0 92u 100% 13u "$StoreName"
  Pop $StoreNameField

  ${NSD_CreateLabel} 0 114u 100% 10u "Nome deste computador (usado no modo monitorado):"
  Pop $0
  ${NSD_CreateText} 0 126u 100% 13u "$MachineName"
  Pop $MachineNameField

  ${NSD_CreateLabel} 0 148u 100% 10u "Porta HTTPS do servidor da loja (padrao 8443):"
  Pop $0
  ${NSD_CreateNumber} 0 160u 32% 13u "$Port"
  Pop $PortField

  ${NSD_CreateLabel} 0 180u 100% 10u "IP desta maquina (vazio = detectar automaticamente):"
  Pop $0
  ${NSD_CreateText} 0 192u 40% 13u "$LanIp"
  Pop $LanIpField

  ${NSD_CreateLabel} 0 212u 100% 10u "Rede local autorizada (CIDR):"
  Pop $0
  ${NSD_CreateText} 0 224u 40% 13u "$LocalSubnet"
  Pop $SubnetField

  nsDialogs::Show
FunctionEnd

Function ModePageLeave
  ${NSD_GetState} $ModeServerRadio $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $Mode "server"
  ${Else}
    StrCpy $Mode "agent"
  ${EndIf}
  ${NSD_GetText} $StoreNameField $StoreName
  ${NSD_GetText} $MachineNameField $MachineName
  ${NSD_GetText} $PortField $Port
  ${NSD_GetText} $LanIpField $LanIp
  ${NSD_GetText} $SubnetField $LocalSubnet
  ${If} $StoreName == ""
    MessageBox MB_ICONEXCLAMATION "Informe o nome da loja."
    Abort
  ${EndIf}
  ${If} $MachineName == ""
    MessageBox MB_ICONEXCLAMATION "Informe o nome deste computador."
    Abort
  ${EndIf}
FunctionEnd

Section "Instalacao" SEC_MAIN
  SectionIn RO
  SetOutPath "$INSTDIR"
  SetOverwrite on
  File /r "${BUNDLE_DIR}\*.*"

  ; O bundle precisa trazer estes itens; falhar aqui e melhor que
  ; instalar e descobrir na primeira execucao.
  ${IfNot} ${FileExists} "$INSTDIR\${APP_EXE}"
    MessageBox MB_ICONSTOP "Pacote incompleto: ${APP_EXE} ausente."
    Abort
  ${EndIf}
  ${IfNot} ${FileExists} "$INSTDIR\install-service.ps1"
    MessageBox MB_ICONSTOP "Pacote incompleto: install-service.ps1 ausente."
    Abort
  ${EndIf}
  ${IfNot} ${FileExists} "$INSTDIR\winsw.exe"
    MessageBox MB_ICONSTOP "Pacote incompleto: winsw.exe ausente."
    Abort
  ${EndIf}

  ; WebView2: instalacao OFFLINE com o pacote completo, sem baixar nada.
  ReadRegStr $0 HKLM "${WEBVIEW2_KEY}" "pv"
  ${If} $0 == ""
    ReadRegStr $0 HKCU "SOFTWARE\Microsoft\EdgeUpdate\Clients\${F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${EndIf}
  ${If} $0 == ""
    ${If} ${FileExists} "$INSTDIR\vendor\${WEBVIEW2_INSTALLER}"
      DetailPrint "Instalando o WebView2 Runtime (pacote offline)..."
      ExecWait '"$INSTDIR\vendor\${WEBVIEW2_INSTALLER}" /silent /install' $1
      ${If} $1 != "0"
        MessageBox MB_ICONEXCLAMATION "O WebView2 Runtime nao foi instalado (codigo $1). A janela pode nao abrir; instale o runtime e execute novamente."
      ${EndIf}
    ${Else}
      MessageBox MB_ICONEXCLAMATION "O pacote offline do WebView2 nao esta presente. Instale o WebView2 Runtime antes de usar a janela."
    ${EndIf}
  ${EndIf}

  DetailPrint "Configurando e registrando o servico (modo $Mode)..."
  nsExec::ExecToLog 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\install-service.ps1" -Mode $Mode -InstallDir "$INSTDIR" -Port $Port -StoreName "$StoreName" -MachineName "$MachineName" -LocalSubnet "$LocalSubnet" -LanIp "$LanIp" -Action install'
  Pop $0
  ${If} $0 == "72"
    MessageBox MB_ICONSTOP "A porta $Port ja esta em uso por outro programa. Clique em Voltar e escolha outra porta."
    Abort
  ${EndIf}
  ${If} $0 != "0"
    MessageBox MB_ICONSTOP "Nao foi possivel configurar o servico (codigo $0). Consulte $PROGRAMDATA\HUBMonitor\logs e execute o instalador novamente."
    Abort
  ${EndIf}

  # Resultado do teste de conectividade, como o pedido exige.
  ${IfNot} ${Silent}
    ${If} $Mode == "server"
      MessageBox MB_OK|MB_ICONINFORMATION "Teste de conectividade concluido. O servidor esta respondendo em HTTPS; a pagina de configuracao vai abrir."
    ${Else}
      MessageBox MB_OK|MB_ICONINFORMATION "Teste de conectividade concluido. Agora importe o arquivo .hubconn da loja na janela do agente."
    ${EndIf}
  ${EndIf}

  WriteRegStr HKLM "${REG_APP}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "${REG_APP}" "Mode" "$Mode"
  WriteRegStr HKLM "${REG_APP}" "HttpsPort" "$Port"
  WriteRegStr HKLM "${REG_UNINSTALL}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKLM "${REG_UNINSTALL}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "${REG_UNINSTALL}" "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKLM "${REG_UNINSTALL}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
  WriteRegStr HKLM "${REG_UNINSTALL}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKLM "${REG_UNINSTALL}" "NoModify" 1
  WriteRegDWORD HKLM "${REG_UNINSTALL}" "NoRepair" 1
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\HUB Monitoramento"
  CreateShortcut "$SMPROGRAMS\HUB Monitoramento\HUB Monitoramento.lnk" "$INSTDIR\${APP_EXE}" "ui"
  CreateShortcut "$DESKTOP\HUB Monitoramento.lnk" "$INSTDIR\${APP_EXE}" "ui"

  ; Icone na bandeja ao entrar no Windows.
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "HUBMonitorTray" '"$INSTDIR\${APP_EXE}" ui --tray-only'

  ${If} $Mode == "server"
    ExecShell "open" "https://127.0.0.1:$Port/configuracao"
  ${EndIf}
SectionEnd

Section "Uninstall"
  nsExec::ExecToLog 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\install-service.ps1" -Mode server -InstallDir "$INSTDIR" -Action remove'
  nsExec::ExecToLog 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\install-service.ps1" -Mode agent -InstallDir "$INSTDIR" -Action remove'
  DeleteRegValue HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "HUBMonitorTray"
  DeleteRegKey HKLM "${REG_UNINSTALL}"
  DeleteRegKey HKLM "${REG_APP}"
  Delete "$SMPROGRAMS\HUB Monitoramento\HUB Monitoramento.lnk"
  RMDir "$SMPROGRAMS\HUB Monitoramento"
  Delete "$DESKTOP\HUB Monitoramento.lnk"

  ; A configuracao (inclusive a credencial dos caixas) vive na pasta do
  ; programa. Sem esta copia, desinstalar invalidaria todos os .hubconn
  ; ja distribuidos.
  %%{If} %%{FileExists} "$INSTDIR\.env"
    CreateDirectory "$PROGRAMDATA\HUBMonitor"
    CopyFiles /SILENT "$INSTDIR\.env" "$PROGRAMDATA\HUBMonitor\config-backup.env"
  %%{EndIf}

  RMDir /r "$INSTDIR"

  ; Historico, certificados e a copia da configuracao ficam em ProgramData.
  MessageBox MB_YESNO|MB_DEFBUTTON2 "Deseja apagar tambem o historico, as configuracoes e os certificados da loja? Escolha Nao para preservar os dados." IDNO KeepData
    RMDir /r "$PROGRAMDATA\HUBMonitor"
    Goto Done
  KeepData:
    DetailPrint "Dados preservados em $PROGRAMDATA\HUBMonitor"
  Done:
SectionEnd
