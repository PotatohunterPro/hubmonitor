---
tipo: recomendacao-arquitetura
status: proposta
atualizado: 2026-10-21
aliases:
  - Hospedagem UniFi
  - UniFi na VPS
tags:
  - hub-monitoramento
  - unifi
  - hospedagem
---

# Recomendação: sistema HUB e controlador UniFi

> [!summary] Decisão de piloto
> O usuário escolheu avaliar HUB e UniFi OS Server na mesma VPS no piloto, depois de medir compatibilidade, recursos e conflitos de portas/serviços. Se o preflight falhar, parar antes de instalar e apresentar alternativas para nova decisão. Isso não decide co-hospedagem em produção. O U6+ é AP Wi-Fi; o MikroTik é o gateway no padrão descrito.

O usuário confirmou que os U6+ já estão adotados em controllers existentes e escolheu migração gradual por cliente. Os modelos/tipos/versões ainda não foram inventariados. Nenhum dispositivo foi migrado ou configurado.

## Por que não instalar um controlador único sem inventário

O controlador UniFi administra os dispositivos UniFi compatíveis. Ele não substitui o monitor HUB: não mede sozinho notebook → MikroTik, não representa todas as WANs e não dá telemetria equivalente a um agente dentro de cada rede.

A Ubiquiti descreve um modelo com plano de controle local e acesso multi-site pelo Site Manager. Essa opção permite manter gateways/controladores nos sites e ainda obter visão administrativa central. Em algumas redes, é mais simples do que levar tráfego de gerenciamento de todas as unidades até um datacenter.

**Regra de compatibilidade importante:** UniFi OS Server não pode gerenciar um Cloud Gateway (por exemplo UDM/UCG), que já inclui o aplicativo UniFi Network no próprio plano de controle. Um dispositivo deve permanecer associado a um único host/controlador. Primeiro identificar quem controla cada AP hoje. Sites com Cloud Gateway ficam fora da migração para este controller e exigem integração/decisão própria.

## Opções

| Opção | Quando escolher | Minha avaliação |
|---|---|---|
| Controlador atual por cliente + Site Manager | Cliente tem UDM/UCG, CloudKey ou controller que já funciona e não será migrado nesta etapa | Manter onde há Cloud Gateway ou incompatibilidade; integração de leitura ao HUB depende de API/versão e credencial. |
| UniFi OS Server em VPS dedicada | Sites têm APs/switches UniFi e gateway de terceiro como MikroTik, sem Cloud Gateway que precise ser gerenciado por ele | Boa opção para gestão central de UniFi; instalar por sites, após piloto e prova de acesso entre cada site e a VPS. |
| HUB + UniFi OS Server na mesma VPS | Piloto solicitado pelo usuário, após preflight e plano de recuperação | Decidido somente para avaliação do piloto; disputa por recursos/portas e falha comum podem afetar painel e controller. Produção permanece pendente. |
| Serviço oficial de hospedagem UniFi | Quer terceirizar manutenção do plano de controle e aceita serviço/custo externo | Alternativa a comparar com autohospedagem. O sistema de monitoramento da HUB continua na VPS própria. |

## Se os dois ficarem na mesma VPS

A versão atual para autohospedagem é **UniFi OS Server**, que substitui o legado UniFi Network Server. Para Linux, a documentação atual lista Ubuntu 24.04 ou posterior, Debian 13 ou posterior (ou distribuição compatível), CPU x86-64, pelo menos 2 GB RAM e 10 GB livres para UniFi OS Server. Esses mínimos são para o produto UniFi; não dimensionam o banco/histórico do HUB, múltiplos clientes, backups nem margem de operação.

O UniFi OS Server não é um simples container Docker/Podman portátil: a Ubiquiti diz que a solução depende de serviços no host. Antes de co-hospedar, levantar sistema operacional/arquitetura, CPU/RAM/disco, portas e serviços ocupados, publicação HTTPS, atualização, backups separados e restauração. Os mínimos oficiais do UniFi não dimensionam HUB, banco/histórico, clientes nem margem operacional. Não comprar nem redimensionar VPS com base só nesses mínimos.

**Gate do piloto:** registrar o resultado do preflight antes de instalar. Se OS, recursos, portas, backup ou retorno forem insuficientes, interromper co-hospedagem e apresentar as opções (separar controller, contratar hosting oficial ou rever capacidade) para decisão; não escolher e instalar uma alternativa automaticamente.

O UniFi OS Server deve permanecer ligado para administrar os dispositivos; quando fica indisponível, os dispositivos adotados continuam com a última configuração, mas não podem ser gerenciados até o retorno. Co-hospedar o HUB aumenta o impacto de uma queda da VPS.

## Rede entre sites e controlador

Para adoção remota camada 3, a documentação da Ubiquiti exige conectividade TCP 8080 entre o dispositivo UniFi e a aplicação; a referência de portas também lista UDP 3478 para STUN/comunicação, além de outras portas conforme os recursos usados.

O usuário escolheu WireGuard como modalidade prioritária da coleta sem PC. Para o piloto, revisar modelo/versão RouterOS, peers, endereços do túnel, rotas de retorno, redes sobrepostas e acesso mínimo ao controller. Permitir pelo túnel apenas tráfego necessário; não expor API/WinBox/SSH do MikroTik publicamente. A adoção camada 3 exige conectividade TCP 8080; revisar outros fluxos conforme recursos usados e versão instalada.

Nenhum túnel ou regra foi criado. Instalar/migrar controller e configurar WireGuard afetam ambiente ativo e exigem inventário, janela, autorização e plano de retorno.

## Como o HUB obterá dados

Manter o monitor HUB como fonte central de clientes, medições, incidentes e histórico. No MVP, consultar somente estado online/frescor do U6+ pela integração/API de leitura que a versão do controller disponibilizar. Vincular cada consulta ao cliente/site cadastrado e proteger a credencial. Se a fonte UniFi estiver indisponível, AP fica desconhecido/obsoleto salvo evidência independente.

Mesmo com controller hospedado na VPS, medições como `Notebook 1 → MikroTik` exigem agente no notebook. Um probe da VPS/UniFi Server não pode receber esse rótulo.

## Próximos passos

1. Inventariar por unidade o MikroTik/RouterOS, U6+, controller atual/tipo/versão, responsável, redes e acesso autorizado.
2. Fazer preflight da VPS do piloto: OS, CPU/RAM/disco, portas/serviços, HTTPS, backup e recuperação. Não instalar se reprovar.
3. Fazer uma migração controlada por cliente: manter controller antigo, atualizar/instalar o novo, exportar backup `.unf`, restaurar/importar e confirmar o AP online/serviço Wi-Fi antes de esquecer ou desligar o antigo.
4. Se AP não retornar, usar o procedimento oficial de migração/adoção camada 3 e revisar conectividade. Factory reset é último recurso e exige autorização específica.
5. Confirmar API, escopo, alertas e retorno; depois planejar o próximo cliente. A escala de produção e hospedagem definitiva continuam pendentes.

## Referências oficiais

- [Self-Hosting UniFi / UniFi OS Server](https://help.ui.com/hc/en-us/articles/34210126298775-Self-Hosting-UniFi)
- [Understanding UniFi Cloud Architecture](https://help.ui.com/hc/en-us/articles/30319146145175-Understanding-UniFi-Cloud-Architecture)
- [Required Ports Reference](https://help.ui.com/hc/en-us/articles/218506997-Required-Ports-Reference)
- [Remote Adoption (Layer 3)](https://help.ui.com/hc/en-us/articles/204909754-Remote-Adoption-Layer-3)
- [Backups and Migration in UniFi](https://help.ui.com/hc/en-us/articles/360008976393-Backups-and-Migration-in-UniFi)
- [[02 - Arquitetura/Visão da arquitetura]] · [[02 - Arquitetura/Coleta e significado das métricas]]
