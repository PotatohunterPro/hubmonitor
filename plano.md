---
tipo: plano
status: direcao-definida
atualizado: 2026-10-20
tags:
  - hub-monitoramento
---

# Plano atual — central de monitoramento na VPS

> [!important] Direção definida em 20/10/2026
> O usuário quer endpoint e dashboard na própria VPS, com visão de vários clientes. O MVP foi delimitado nesta conversa: MikroTik, estado individual das WANs, U6+ online, histórico e alertas no painel e Telegram; computadores depois. Esta atualização é **somente documentação**. A central ainda não foi implementada nem implantada.

## 1. Objetivo

A HUB deve abrir um único painel, localizar um cliente, entender a saúde da rede e investigar cada equipamento ou caminho com histórico e evidências. Exemplo solicitado: **Palone → MikroTik → WAN 1 / WAN 2 / WAN 3, UniFi e Notebook 1**. Os nomes e números do exemplo não comprovam inventário ou medições reais.

A descrição recomendada é **HUB Monitoramento — central de análise de redes dos clientes**. A estrutura é cliente → unidade → dispositivos, links e medições. O primeiro acesso é para a equipe HUB; portal de cliente fica para decisão posterior.

## 2. Direção confirmada e propostas

| Tema | Situação |
|---|---|
| Endpoint e dashboard na VPS do usuário | Direção confirmada; recursos, sistema e domínio ainda não informados. |
| Visão por cliente, rede, equipamento e WAN | Direção confirmada. |
| Atender clientes com e sem computador sempre ligado | Requisito confirmado; computadores não entram no MVP. |
| Coleta sem PC por WireGuard | Modalidade prioritária escolhida; compatibilidade, rotas e autorização ainda precisam ser verificadas. Nenhum túnel foi configurado. |
| Acesso ao dashboard | Somente equipe HUB no MVP; sem portal de cliente. |
| Alertas | Incidentes no painel e notificações pelo Telegram para a equipe HUB. |
| UniFi OS Server junto ao HUB | Avaliar na mesma VPS no piloto, condicionado a preflight. Co-hospedagem em produção continua sem decisão. |
| Migração UniFi | U6+ existentes estão adotados em controllers; migração gradual por cliente, após inventário e backup. |
| Piloto Palone | Candidato se acesso e autorização forem confirmados; inventário e WANs reais ainda desconhecidos. |
| Banco central, retenção, escala e capacidade final da VPS | Decisões técnicas pendentes; não presumir aprovação de stack ou dimensionamento. |
| Implementar, publicar, instalar, mudar rede ou testar em cliente | Fora desta atualização documental. Executar somente com escopo/autorização próprios. |

A decisão está em [[02 - Arquitetura/Decisões/ADR-001 - Central na VPS]].

## 3. Painel completo desejado

- Visão geral com clientes, unidades, incidentes, ausência de dados e saúde da própria central.
- Página do cliente com topologia, equipamentos, WANs, Wi-Fi, qualidade da rede e linha do tempo.
- MikroTik: disponibilidade observada, interfaces, tráfego, recursos quando disponíveis e saúde independente de cada WAN.
- UniFi: dispositivos, uplink e clientes Wi-Fi, conforme controller/API/modelo disponíveis.
- Computadores: presença e conectividade; medição computador → gateway feita no próprio computador. Saúde de CPU/memória/disco é expansão planejada, dependente de agente e capacidade.
- Gráficos com latência, perda, variação de latência, tráfego, quedas e recuperação; comparar caminhos no mesmo período.
- Incidentes correlacionados, manutenção, reconhecimento e histórico; notificações com destinatários separados por cliente.
- Inventário e cobertura: mostrar o que está monitorado, o que está sem coleta e o que o equipamento não suporta.

### Recorte confirmado do MVP

- Acesso da equipe HUB, sem contas de cliente no primeiro release.
- Estado de comunicação do MikroTik, estado individual de cada WAN, estado online do U6+, linha do tempo e incidentes básicos.
- Alertas visíveis no painel e enviados ao destino interno do Telegram.
- Computadores, agente de endpoint, métricas de hardware, RTT de notebook para gateway e topologia Wi-Fi detalhada ficam para evolução posterior.
- Estado de WAN depende de sinal por link/saída comprovado; sem isso, exibir **não verificada**. Estado do AP deve ficar desconhecido/obsoleto se o controller não responder, salvo evidência independente.

Especificação: [[01 - Projeto/Painel de análise de rede]]. Métricas: [[02 - Arquitetura/Coleta e significado das métricas]].

## 4. Arquitetura e modalidades

No MVP sem computadores, a VPS consulta o MikroTik por uma conexão WireGuard prioritária e coleta os dados UniFi pelo controller central compatível. A API de gestão do MikroTik fica acessível somente pelo caminho privado e com credencial restrita a leitura. A integração, o túnel e a central multi-cliente ainda não existem no código.

Antes de adotar WireGuard em cada unidade, verificar modelo/versão RouterOS, endereçamento do túnel, rotas, redes sobrepostas e retorno. Se não for compatível, interromper a configuração e levar alternativa para nova decisão; não publicar a API de administração na internet como fallback. Se o túnel cair, mostrar perda de comunicação/frescor, não queda comprovada da rede do cliente.

Ler apenas sondas WAN existentes e mapear cada uma à interface/saída real. Sonda pela rota padrão não prova o estado de cada link. Criar/alterar Netwatch, rotas, firewall ou permissões exige levantamento, autorização e plano de retorno próprios.

Detalhes e comparação: [[02 - Arquitetura/Visão da arquitetura]]. Nenhuma alternativa autoriza habilitar serviços ou alterar roteadores agora.

## 5. Primeira entrega confirmada

Palone é candidato a piloto se houver confirmação de acesso e autorização. Antes de conectar, levantar o cliente/unidade, MikroTik, WANs e sondas existentes, RouterOS, controller UniFi, U6+, topologia necessária, responsável e janela.

Avaliar HUB e UniFi OS Server na mesma VPS para o piloto somente após verificar compatibilidade do sistema operacional, CPU/RAM/disco, portas/serviços, backups e recuperação. Se o preflight falhar, parar antes da instalação e registrar alternativas para decisão; não instalar em outro host por inferência.

Migrar U6+ um cliente por vez: backup do controller atual, restauração/importação no novo, confirmação do AP online e da operação Wi-Fi, e só então retirada do controller antigo. Manter exceções incompatíveis fora da migração; nunca usar factory reset como etapa automática.

Para sair do piloto, aceitar: isolamento entre dois clientes de teste; perda do túnel não derruba artificialmente todos os equipamentos; controller indisponível não vira AP offline; WAN sem teste próprio aparece não verificada; histórico preserva origem e horário; alerta chega ao painel e Telegram. Nada disso foi testado nesta atualização.

Topologia avançada, relatórios, métricas Wi-Fi adicionais e saúde ampla de computadores entram depois do núcleo. Veja [[03 - Planejamento/Plano e pendências]].

## 6. Limites e operação

- Não publicar diretamente o painel local atual: as consultas de monitoramento ainda não têm proteção de usuário equivalente à exigida para uma central multiempresa.
- O objetivo passa a ser um serviço HTTPS autenticado na VPS. Gerenciamento de roteadores permanece restrito à rede/VPN, sem exposição pública direta.
- Monitoramento e diagnóstico não alteram automaticamente rotas, firewall, failover, firmware ou configuração dos clientes.
- Ausência de telemetria não comprova que a loja, a internet ou todos os dispositivos caíram.
- Medição fiscal/SEFAZ existente fica como módulo específico a reavaliar; TEF e coleta de conteúdo fiscal/cartões ficam fora deste planejamento.
- Monitoramento contínuo não promete atendimento humano 24/7 nem SLA. Preços e cobertura comercial precisam ser redesenhados.

## 7. Estado e próximo passo

O código permanece na arquitetura local anterior. Inspeção de arquivos nesta revisão identificou autenticação administrativa e de ingestão, mas consultas como `/status`, `/machines` e `/wans` sem exigência de sessão nos handlers. Isto é leitura estática, não auditoria completa nem teste executado.

Próximo passo: inventariar recursos/OS/portas da VPS e levantar Palone com acesso autorizado; verificar RouterOS/WireGuard, probes WAN e controller/backup UniFi. Banco, retenção, escala e hospedagem UniFi de produção permanecem pendentes antes de qualquer implementação.

Histórico preservado em [[99 - Arquivo/2026-10-20 - Plano anterior local por loja]].
