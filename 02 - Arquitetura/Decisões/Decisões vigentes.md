---
tipo: decisoes
status: vigente
atualizado: 2026-10-20
aliases:
  - Decisões
  - ADRs
tags:
  - hub-monitoramento
---

# Decisões vigentes

## Confirmadas pelo usuário

| ID | Decisão | Fonte / data |
|---|---|---|
| D01 | Endpoint e painel na VPS do usuário | Pedido de 20/10/2026; [[02 - Arquitetura/Decisões/ADR-001 - Central na VPS]] |
| D02 | Visão de vários clientes com detalhe de rede, MikroTik, WANs, UniFi e computadores | Mesmo pedido; [[01 - Projeto/Painel de análise de rede]] |
| D03 | Prever locais com e sem máquina sempre ligada | Resposta do usuário em 20/10/2026 |
| D04 | Etapa atual somente Markdown e planejamento | Pedido explícito: não mexer em código agora |
| D05 | MVP: acesso da equipe HUB; MikroTik, estado de cada WAN, U6+ online, histórico e alertas no painel e Telegram; computadores depois | Respostas do usuário em 20/10/2026 |
| D06 | WireGuard como modalidade prioritária para coleta remota sem PC | Resposta do usuário em 20/10/2026; compatibilidade e configuração ainda pendentes |
| D07 | Avaliar HUB e UniFi OS Server na mesma VPS durante o piloto, após preflight de compatibilidade, recursos e conflitos | Resposta do usuário em 20/10/2026; não aprova co-hospedagem de produção |
| D08 | Migrar gradualmente, por cliente, os U6+ já adotados em controllers existentes | Resposta do usuário em 20/10/2026; tipo/versão dos controllers ainda desconhecidos |
| D09 | Palone é candidato a piloto apenas se acesso e autorização forem confirmados | Resposta do usuário em 20/10/2026; inventário ainda pendente |

## Regras preservadas

- A coleta/diagnóstico não deve alterar automaticamente equipamentos.
- Mostrar evidências e limitações; não inventar causa, resultado, cobertura, preço ou SLA.
- Proteger credenciais e separar dados dos clientes.
- Manter histórico; documentação não comprova integração ou teste ao vivo.

## Propostas, ainda dependentes de escolha

| Tema | Recomendação de trabalho | Pendência |
|---|---|---|
| Coleta do MVP sem PC | WireGuard é a prioridade; consultar o MikroTik por canal privado e credencial de leitura | Compatibilidade RouterOS/modelo, isolamento de rotas e autorização por unidade |
| Agentes/coletor dedicado | Evolução para medições originadas em PCs e cobertura complementar | Escopo, hardware, empacotamento e custo ficam para etapa posterior |
| Stack | Avaliar reaproveitar Python/FastAPI; PostgreSQL candidato central; SQLite candidato à fila | Dimensionamento e ADR técnico antes de implementar |
| VPS/UniFi | Co-hospedar HUB e UniFi OS Server apenas como piloto condicionado ao preflight | Compatibilidade/recursos/portas/recuperação; hospedagem em produção continua pendente |
| Migração UniFi | Migrar U6+ gradualmente por cliente, mantendo o controller antigo até confirmação no novo | Tipo/versão, backup, portas e janela por cliente |
| Produto inicial | Painel HUB-only para MikroTik, WANs, U6+, histórico e alertas painel/Telegram | Capacidades por versão e qualidade das sondas WAN precisam ser levantadas |
| Palone | Candidato condicional ao acesso e autorização | Responsável, inventário real e janela |
| Comercial | Rever implantação + mensalidade com custo por unidade/dispositivos | Valores, limites e atendimento |

## Decisões superadas

- “Plataforma multiempresa fora do primeiro escopo”: substituída por D01/D02.
- “Servidor e banco exclusivamente por loja”: substituída como arquitetura-alvo; descreve a base antiga.
- “Até três caixas como faixa-base”: modelo comercial anterior, não aprovado para a nova central.
- “Painel somente LAN” como objetivo de produto: substituído por central autenticada. O painel local existente segue sem autorização para exposição direta.

## Como decidir daqui para frente

Manter [[03 - Planejamento/Decisões pendentes]] como fila. Cada escolha durável registra data, origem, alternativas e consequência usando [[90 - Modelos/Modelo de decisão]]. Aprovação da direção não significa aprovação automática de toda tecnologia sugerida.
