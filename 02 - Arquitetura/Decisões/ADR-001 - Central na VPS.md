---
tipo: decisao
status: direcao-aprovada
atualizado: 2026-10-21
tags:
  - hub-monitoramento
---

# ADR-001 — Central na VPS

## Situação

**Direção aprovada pelo usuário em 20/10/2026; implementação pendente.** O escopo do MVP e algumas preferências operacionais foram confirmados depois, em respostas na mesma data; tecnologias/compatibilidade ainda dependem de levantamento.

## Contexto e fonte

O usuário pediu endpoint hospedado na própria VPS, dashboard dos clientes e detalhamento: Palone online; MikroTik com WAN 1/2/3; UniFi e Notebook 1 com qualidade do caminho até o MikroTik. Pediu atualização dos Markdown para acompanhamento no Obsidian e determinou “não mexa em código agora”.

Ao perguntar sobre uma máquina sempre ligada, respondeu: **“Depende do cliente; precisamos prever as duas situações”.**

Em respostas posteriores, o usuário confirmou o MVP (MikroTik, estado individual das WANs, U6+ online, histórico e alertas no painel/Telegram; computadores depois), acesso somente para a equipe HUB, WireGuard como prioridade de coleta sem PC, co-hospedagem do HUB e UniFi OS Server na mesma VPS apenas durante o piloto após preflight, migração gradual dos U6+ e Palone como candidato condicionado a acesso/autorização.

## Decisão confirmada

1. Centralizar endpoint e dashboard na VPS.
2. Organizar clientes/unidades e seus equipamentos/links.
3. Incluir análise da rede, MikroTik, WANs, UniFi e computadores como direção do produto.
4. Prever instalações com e sem computador sempre ligado.
5. MVP para a equipe HUB: estado do MikroTik, estado de cada WAN, U6+ online, histórico e alertas no painel e Telegram; computadores ficam para etapa posterior.
6. Priorizar WireGuard para coleta remota sem PC, sem publicar gestão do MikroTik como fallback automático.
7. Avaliar HUB e UniFi OS Server na mesma VPS somente no piloto e após preflight; produção não foi decidida.
8. Migrar os U6+ já adotados por cliente, gradualmente e após backup/validação do controller novo.
9. Considerar Palone como piloto somente após confirmação de acesso e autorização.
10. Nesta atualização, alterar somente documentação; código, rede e integrações não serão modificados.

## Recomendações ainda não aprovadas como solução final

- Agentes de PC e coletores locais/dedicados para evolução posterior.
- WireGuard priorizado no MVP, condicionado a compatibilidade do MikroTik, isolamento de rotas, inventário e autorização; nenhum túnel está configurado.
- FastAPI/Python reaproveitados, banco central, retenção e frontend ainda dependem de decisão técnica.
- Piloto Palone condicionado a acesso/autorização, inventário, sondas WAN e tipo/versão do controller.
- Co-hospedagem na VPS é somente avaliação de piloto; se o preflight falhar, parar e registrar alternativas para nova decisão.

## Consequências

- Substitui a decisão de adiar central multiempresa e manter painel somente local como arquitetura-alvo.
- A restrição de não expor o painel **existente** continua válida até haver autenticação e isolamento adequados.
- Preserva leitura de equipamentos, evidência para diagnóstico, proteção de segredos e necessidade de autorização para mudanças de rede.
- Cada WAN só recebe estado positivo/negativo quando houver fonte e saída independentes comprovadas; sem isso, fica “não verificada”. Indisponibilidade do túnel/controlador resulta em falta de comunicação ou estado desconhecido, não em queda automática de toda a rede/AP.
- Migração UniFi exige backup do controller original, confirmação dos dispositivos no destino e só depois retirada do original; reset de fábrica não é etapa automática.
- A oferta de até três caixas e o instalador antigo precisam ser reavaliados; não representam automaticamente o novo produto.
- Exige definir autenticação, isolamento de clientes, conectividade dos sensores, retenção, backups e observabilidade da VPS.

## Documentos substituídos e relacionados

- [[99 - Arquivo/2026-10-20 - Plano anterior local por loja]]
- [[99 - Arquivo/2026-10-20 - Oferta anterior caixa e conectividade]]
- [[plano]] · [[02 - Arquitetura/Visão da arquitetura]] · [[03 - Planejamento/Decisões pendentes]]
