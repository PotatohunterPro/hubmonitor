---
tipo: indice
status: vigente
atualizado: 2026-10-20
aliases:
  - Início
  - Home
tags:
  - hub-monitoramento
---

# HUB Monitoramento — memória do projeto

> [!important] Leia primeiro
> **Direção atual: central na VPS para análise de redes de vários clientes.** MVP restrito à equipe HUB: MikroTik, WANs, U6+, histórico e alertas. Esta vault registra decisões e planejamento; a central e a integração UniFi ainda não existem.

## Retomar em poucos minutos

1. [[01 - Projeto/Contexto para agentes]] — objetivo, limites e onde paramos.
2. [[plano]] — escopo atual e separação entre decisões e propostas.
3. [[03 - Planejamento/Plano e pendências]] — sequência e próxima ação.

**Fluxo desejado:** clientes/unidades → MikroTik e WANs + APs UniFi → histórico, incidentes e evidências. Palone é candidato a piloto somente após confirmação de acesso e autorização. Notebooks ficam para etapa posterior.

## Navegação

| Área | Notas |
|---|---|
| Produto | [[01 - Projeto/Sobre o projeto]] · [[01 - Projeto/Painel de análise de rede]] |
| Arquitetura | [[02 - Arquitetura/Visão da arquitetura]] · [[02 - Arquitetura/Recomendação de hospedagem UniFi]] · [[02 - Arquitetura/Coleta e significado das métricas]] |
| Decisões | [[02 - Arquitetura/Decisões/Decisões vigentes]] · [[02 - Arquitetura/Decisões/ADR-001 - Central na VPS]] |
| Tecnologias | [[02 - Arquitetura/Tecnologias/Stack atual]] |
| Planejamento | [[03 - Planejamento/Plano e pendências]] · [[03 - Planejamento/Decisões pendentes]] |
| Aceite futuro | [[04 - Testes/Plano de aceite]] |
| Operação | [[05 - Operação/Instalação e segurança]] · [[05 - Operação/Levantamento do piloto Palone]] |
| Fontes | [[06 - Referências/Mapa de fontes]] |
| Modelos | [[90 - Modelos/Modelo de decisão]] · [[90 - Modelos/Modelo de registro]] |
| Histórico | [[99 - Arquivo/Histórico e conteúdo superado]] |

## Onde paramos — 20/10/2026

- Decisões do MVP: HUB interno; MikroTik, estado de cada WAN, U6+ online, histórico e alertas no painel e Telegram. Computadores ficam para a etapa seguinte.
- WireGuard é a modalidade prioritária para coleta sem PC. Compatibilidade do RouterOS, rotas e sondas WAN ainda precisam de levantamento; nenhum túnel foi criado.
- HUB e UniFi OS Server serão avaliados na mesma VPS no piloto, após preflight. A produção ainda não tem decisão de hospedagem do controller.
- Migração gradual por cliente dos U6+ já adotados em controllers existentes. Palone é candidato condicionado a acesso e autorização confirmados; inventário ainda não validado.
- Esta atualização é somente Markdown. A central, integração UniFi e isolamento multi-cliente não foram implementados; não houve teste nem validação em cliente.
- Próximo passo documental: concluir preflight da VPS e inventário autorizado do piloto; o envio ao GitHub requer revisão dos artefatos locais, pois a origem indicada é pública.

## Manutenção da memória

Leia [[AGENTS]] no início. Atualize a nota responsável pelo assunto e o resumo do estado quando uma decisão mudar. Registre data, origem e evidência; arquive escolhas superadas. Use wikilinks e propriedades `tipo`, `status`, `atualizado`. Os modelos estão em `90 - Modelos`, no plugin nativo Modelos. Nenhum plugin comunitário é necessário.

Não guardar credenciais nem transformar propostas, mockups ou exemplos em resultados reais.
