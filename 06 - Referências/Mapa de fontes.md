---
tipo: referencias
status: vigente
atualizado: 2026-10-20
aliases:
  - Fontes
  - Referências
tags:
  - hub-monitoramento
---

# Mapa de fontes

## Qual fonte responde a qual pergunta

| Fonte | Uso | Limite |
|---|---|---|
| [[AGENTS]] e [[01 - Projeto/Contexto para agentes]] | Retomar trabalho e respeitar limites | Não substituem evidência atual |
| [[plano]] | Direção e escopo atuais | Planejamento, não implementação |
| [[02 - Arquitetura/Decisões/ADR-001 - Central na VPS]] | Origem da mudança e requisito das duas situações de coleta | Tecnologias/modalidades finais pendentes |
| [[01 - Projeto/Painel de análise de rede]] | Requisitos do painel e navegação | Exemplo ilustrativo sem telemetria real |
| [[02 - Arquitetura/Visão da arquitetura]] | Componentes e alternativas | Arquitetura proposta |
| [[02 - Arquitetura/Recomendação de hospedagem UniFi]] | Hospedagem do controller, compatibilidade e rede entre sites | Recomendação condicional; conferir modelos e controller em cada unidade |
| [[02 - Arquitetura/Coleta e significado das métricas]] | Origem, qualidade e critérios de leitura | Intervalos/limiares a calibrar |
| [[03 - Planejamento/Plano e pendências]] | Sequência e estado de trabalho | Marcar feito só com evidência adequada |
| [[03 - Planejamento/Decisões pendentes]] | Próximas escolhas | Recomendações não são aprovações |
| [[05 - Operação/Levantamento do piloto Palone]] | Inventário a confirmar | Palone ainda é candidato a piloto |
| [[04 - Testes/Plano de aceite]] | Aceite futuro da central | Não executado nesta revisão |
| [[README]] e código | Base local existente e reaproveitamento | Não representam central implementada |
| [[OFERTA_HUB_MONITOR]] | Proposta comercial em revisão | Sem preço ou cobertura fechados |
| [[docs/GUIA_INSTALACAO]] / [[docs/ROTEIRO_TESTE_BERTOLO]] | Procedimentos anteriores de loja | Não são deploy/aceite da VPS |
| [[docs/RELATORIO_ENTREGA]] | Relatório de 17/10/2026 | Preservar como evidência datada |
| [[PLANO_ACAO_WINDOWS]] / [[plano_historico]] | Planejamentos anteriores | Não usar como objetivo atual |
| [[99 - Arquivo/Histórico e conteúdo superado]] | Escolhas substituídas e versões preservadas | Histórico |

## Fontes oficiais consultadas em 20/10/2026

- [RouterOS REST API](https://manual.mikrotik.com/docs/developer-guides/rest-api/): a interface permite leitura e também operações de alteração; o conector de monitoramento precisa restringir operações/permissões e usar transporte protegido. Recursos e sintaxe devem ser conferidos para a versão do cliente.
- [RouterOS Netwatch](https://manual.mikrotik.com/docs/diagnostics-monitoring-and-troubleshooting/netwatch/): referência para interpretar sondas existentes. Consultar definição e caminho efetivo antes de associar um resultado a uma WAN.
- [UniFi OS Server — autohospedagem](https://help.ui.com/hc/en-us/articles/34210126298775-Self-Hosting-UniFi): versão atual, requisitos de host e limitações com Cloud Gateways.
- [Backup e migração UniFi](https://help.ui.com/hc/en-us/articles/360008976393-Backups-and-Migration-in-UniFi): referência para backup/restauração durante migração gradual. Fazer backup antes de cada cliente e manter o controller antigo até confirmar o dispositivo no destino.
- [Adoção remota camada 3](https://help.ui.com/hc/en-us/articles/204909754-Remote-Adoption-Layer-3): referência oficial para o fluxo de adoção; requer conectividade de gestão, incluindo TCP 8080. Conferir compatibilidade e portas adicionais antes do piloto.
- [UniFi Cloud Architecture](https://help.ui.com/hc/en-us/articles/30319146145175-Understanding-UniFi-Cloud-Architecture): controle por site e administração pelo Site Manager.
- [Portas UniFi](https://help.ui.com/hc/en-us/articles/218506997-Required-Ports-Reference) e [adoção remota camada 3](https://help.ui.com/hc/en-us/articles/204909754-Remote-Adoption-Layer-3): fluxo de comunicação que precisa ser aprovado por rede.
- [UniFi — listagem de dispositivos adotados](https://developer.ui.com/network/v10.6.106/getadopteddeviceoverviewpage): exemplo de capacidade documentada por site. Não prova compatibilidade do controller Palone nem medição AP → gateway.

Essas fontes sustentam candidatos de integração, não uma validação da rede do cliente. O desenho de arquitetura e produto na vault é proposta do projeto.

## Evidência local desta revisão

Leitura de `server/main.py` e `server/api/routes.py`: há controles para ingestão/administração, enquanto handlers de consultas como `/status`, `/machines` e `/wans` não exigem sessão. Nenhum teste foi executado. Reexaminar código e política de acesso antes de implementar/publicar a central.

## Anexos

Usar [[06 - Referências/Anexos/README]] para capturas, diagramas e evidências sanitizadas. Nomear com data e assunto; não incluir credenciais ou informações pessoais desnecessárias.
