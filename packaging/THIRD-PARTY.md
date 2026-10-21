# Componentes de terceiros

O HUBMonitor-Setup.exe empacota os itens abaixo. Este arquivo existe
para atender aos avisos de licença e deve acompanhar a distribuição.

| Componente | Uso | Licença |
|-----------|-----|---------|
| Python 3.12 | runtime embutido no bundle | PSF License |
| PyInstaller | empacotamento | GPL-2.0 com exceção de bootloader |
| FastAPI / Starlette | API local | MIT / BSD-3 |
| Uvicorn | servidor ASGI | BSD-3 |
| Pydantic | validação de dados | MIT |
| httpx / httpcore | cliente HTTP | BSD-3 |
| dnspython | consultas DNS | ISC |
| psutil | conexões TCP (TEF) | BSD-3 |
| python-dotenv | leitura de configuração | BSD-3 |
| cryptography | geração do certificado local | Apache-2.0 / BSD-3 |
| Jinja2 | dashboard | BSD-3 |
| librouteros | API RouterOS (somente leitura) | MIT |
| pywebview | janela da interface | BSD-3 |
| pystray | ícone na bandeja | **LGPL-3.0** |
| Pillow | ícone da bandeja | HPND |
| WinSW | wrapper de serviço do Windows | MIT |
| NSIS | gerador do instalador | zlib/libpng |
| Chart.js | gráficos do dashboard | MIT |
| WebView2 Runtime | motor da janela (Microsoft) | Termos Microsoft |
| Raízes ICP-Brasil | validação TLS da SEFAZ | certificados públicos |

## Observações

- **pystray é LGPL-3.0.** Ele é usado como biblioteca, sem modificação,
  e pode ser substituído pelo usuário. O código do HUB Monitoramento
  permanece sob a licença do projeto.
- O **WebView2 Runtime** não é redistribuído como parte do produto: o
  instalador executa o bootstrapper oficial da Microsoft quando o
  runtime não está presente.
- As raízes da ICP-Brasil em `certs/` são certificados **públicos** de
  autoridade certificadora, obtidos de `acraiz.icpbrasil.gov.br`. Não
  há qualquer chave privada ou certificado de cliente no projeto.
