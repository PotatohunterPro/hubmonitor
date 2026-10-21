---
tipo: planejamento
status: acompanhamento
atualizado: 2026-10-21
aliases:
  - Backlog
  - Pendências
tags:
  - hub-monitoramento
---

# Plano e pendências

## Onde paramos — 21/10/2026

O usuário confirmou o MVP HUB-only: MikroTik, estado individual das WANs, U6+ online, histórico e alertas no painel e Telegram; computadores ficam para depois. WireGuard é a modalidade prioritária sem PC. HUB e UniFi OS Server serão avaliados na mesma VPS no piloto, após preflight. U6+ já adotados migram gradualmente por cliente. Palone é candidato somente após acesso e autorização confirmados.

Em 21/10/2026, a vault e a base existente foram publicadas na branch `main` do GitHub (commit `033bde2`). O `.env.example` foi generalizado e arquivos locais/operacionais foram excluídos. **Não houve implementação da central, implantação, migração de controller, mudança de rede, teste ou validação em cliente.** A base atual ainda tem configuração única/global de MikroTik, SQLite e nenhuma integração UniFi/multi-cliente.

**Próxima ação:** inventariar a VPS e Palone com autorização; verificar OS/recursos/portas, RouterOS/WireGuard, probes WAN e controller UniFi/backup antes de instalar ou configurar qualquer coisa. Pendências em [[03 - Planejamento/Decisões pendentes]].

## P0 — fechar desenho, ainda sem código

- [x] Registrar direção e limites em [[02 - Arquitetura/Decisões/ADR-001 - Central na VPS]].
- [x] Documentar [[01 - Projeto/Painel de análise de rede|painel completo proposto]].
- [x] Documentar [[02 - Arquitetura/Visão da arquitetura|modalidades]] e [[02 - Arquitetura/Coleta e significado das métricas|significado das métricas]].
- [x] Preservar plano e oferta anteriores e sinalizar documentação da versão local.
- [ ] Inventariar OS, arquitetura, CPU, RAM, disco, região, domínio e serviços/portas ocupados na VPS; confirmar backups e restauração.
- [ ] Confirmar acesso, responsável, autorização e janela para o candidato Palone; preencher [[05 - Operação/Levantamento do piloto Palone]].
- [ ] Levantar escala inicial e horizonte de 12 meses: clientes, unidades, MikroTik, U6+, WANs e períodos de operação.
- [ ] Verificar compatibilidade de modelo/versão RouterOS com WireGuard; mapear sub-redes repetidas, retorno e endereços de túnel antes de qualquer mudança.
- [ ] Ler somente a configuração/probes WAN existentes e comprovar a saída de cada link; sem teste independente, classificar como não verificada.
- [ ] Inventariar controller UniFi, tipo/versão, credenciais administrativas atuais, método de backup e compatibilidade de migração, sem guardar segredos na vault.
- [ ] Fechar banco central, retenção, volume, intervalos, limiares e política de alerta depois do inventário e preflight.

## P1 — fundação da central, somente após autorização de implementação

- [ ] Modelar cliente/unidade/dispositivo/WAN/controller e identidades de coleta escopadas; manter IP/hostname como atributos mutáveis.
- [ ] Implementar autenticação da equipe HUB e autorização em todas as consultas/ações/exportações; portal do cliente fora do MVP.
- [ ] Vincular credenciais de ingestão ao escopo do sensor, com rotação e revogação.
- [ ] Criar ingestão, persistência, histórico, estados de frescor e saúde da central.
- [ ] Preparar HTTPS, proteção da API, backups/restauração, logs, saúde da central e destino interno Telegram.
- [ ] Implementar coleta de cada MikroTik pelo túnel privado; não abrir gestão pública como fallback.
- [ ] Validar isolamento com dois clientes usando os mesmos IPs e nomes de máquinas.

Saída esperada: base protegida e identificada por cliente, ainda sem promessa de cobertura real de equipamentos.

## P2 — coleta e painel do piloto

- [ ] Implementar cada peer WireGuard e coletor RouterOS com permissão de leitura, escopo por cliente e rotas mínimas aprovadas.
- [ ] Adaptar leitura WAN para N links reais por unidade; mapear fontes independentes e manter sem probe como não verificada.
- [ ] Integrar leitura de estado/frescor do U6+ a partir do UniFi OS Server compatível, com status do controller separado do status do AP.
- [ ] Migrar o controller de um cliente por vez: backup, restore/import, adoção, confirmação do AP/serviço Wi-Fi e só depois retirada do host antigo.
- [ ] Entregar painel HUB-only com MikroTik, WANs, U6+, histórico e incidentes; enviar alertas/recuperações ao Telegram interno.
- [ ] Fazer preflight de co-hospedagem na VPS e interromper se OS, recursos, portas, backups ou recuperação não forem aprovados.
- [ ] Registrar evidências de aceite em [[04 - Testes/Plano de aceite]].

Saída esperada: fluxo ponta a ponta observado no ambiente aprovado, com rótulos corretos e cobertura explícita.

## P3 — segunda modalidade e operação repetível

- [ ] Validar onboarding repetível por cliente, com WireGuard e controller existente migrado gradualmente.
- [ ] Validar segundo cliente de teste e endereços LAN repetidos; demonstrar isolamento dos túneis e dos dados.
- [ ] Calibrar intervalos, limites, retenção e volume na VPS.
- [ ] Validar incidentes, manutenção, painel e Telegram interno; canais por cliente ficam fora do MVP.
- [ ] Produzir processo de onboarding, atualização, remoção e retorno à versão anterior.
- [ ] Medir custo por unidade, esforço de suporte e necessidade de coletor dedicado.

Saída esperada: modalidades com cobertura comprovada e custos conhecidos, antes de ampliar oferta.

## P4 — evolução do painel completo

- [ ] Agentes de computadores, medições originadas nos endpoints e saúde de hardware.
- [ ] Avaliar coletor dedicado para casos em que WireGuard/modelo/topologia não cobrir a necessidade.
- [ ] Topologia com fonte/confiança e inventário de portas/VLANs quando disponível.
- [ ] Wi-Fi detalhado: sinal, canais, retransmissões e histórico de clientes conforme suporte.
- [ ] Comparação de caminhos, baselines e relatórios de recorrência.
- [ ] Relatórios e exportações com cobertura e permissões.
- [ ] Saúde ampla de computadores/servidores e eventual portal do cliente.

## Pendências antigas em reavaliação

Build do `HUBMonitor-Setup.exe`, teste Windows e roteiro Bertolo permanecem sem nova conclusão nesta revisão. Reavaliar o pacote após decidir papéis de coletor/agente e migração. Não marcar como concluídos, nem usar o build antigo como primeiro passo automático da nova central.

## Como encerrar um item

Decisão: data, responsável/origem e nota vinculada. Implementação: arquivos/versão e limites. Teste: ambiente, execução, resultado e evidência. Aprovação de design não encerra item de implementação ou aceite.
