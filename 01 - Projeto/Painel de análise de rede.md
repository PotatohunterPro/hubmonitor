---
tipo: especificacao
status: planejado
atualizado: 2026-10-20
tags:
  - hub-monitoramento
---

# Painel de análise de rede

> [!info] Especificação proposta
> Nenhuma tela desta nota foi implementada. MVP confirmado: painel somente da equipe HUB, MikroTik, estado individual das WANs, U6+ online, histórico e alertas no painel/Telegram. Palone e os valores ilustrativos não são inventário nem telemetria coletada.

## 1. Navegação e prioridade

**Visão geral → Clientes → Unidade → Dispositivo ou link → Histórico/Incidente.** Manter busca por cliente/equipamento, breadcrumb e filtros de período. Priorizar falhas e falta de visibilidade; exibir horário da última atualização em toda tela.

Menu proposto: Visão geral · Clientes · MikroTik/WANs · UniFi · Incidentes · Histórico · Administração. O portal do cliente e os computadores ficam fora do MVP. A saúde do túnel, controller e central deve estar acessível na visão geral.

## 2. Visão geral da HUB

- Totais de clientes/unidades normais, degradados, com falha observada, sem comunicação e em manutenção.
- Incidentes prioritários com duração, clientes afetados, componente, evidência e responsável.
- Tabela: cliente, unidade, conectividade, saúde da rede, WANs disponíveis/monitoradas, dispositivos com falha, cobertura, último contato e incidente principal.
- Filtros por cliente, unidade, estado, fabricante, equipamento crítico e responsável.
- Ordenação padrão por impacto e duração; cliente sem coleta nunca aparece verde só por não ter incidentes.
- Indicador da própria central: ingestão, filas, atualização, banco e notificações. Falha da VPS não deve ser apresentada como queda simultânea de todas as lojas.

## 3. Página do cliente — exemplo conceitual

```text
CLIENTES > CLIENTE A CONFIRMAR > UNIDADE A CONFIRMAR       [período] [atualização]
Coleta: ATUALIZADA | Cobertura: PARCIAL/COMPLETA* | última consulta: horário
* A cobertura depende do inventário e das fontes realmente configuradas.

MikroTik gateway   alcançável pelo WireGuard   [última consulta]
WAN cadastrada 1   não verificada*             [fonte/probe]
UniFi U6+ AP       online pelo controller      [última atualização]
Alertas            1 aberto · painel + Telegram HUB

[Resumo] [WANs] [UniFi] [Incidentes] [Histórico]
```

Não cadastrar WANs ou nomes de cliente como fatos sem inventário. O painel mostra estado de cada WAN como **não verificada** se não houver probe independente associado à saída real. Acesso ao MikroTik pelo túnel prova gestão alcançável pelo túnel, não saúde de toda a LAN. O estado do controller é separado do estado do U6+; se a API/controller não responde, exibir AP desconhecido/obsoleto, salvo evidência independente. RTT do U6+ ao MikroTik e do notebook ao gateway não fazem parte do MVP.

### Resumo e topologia

- Inventário com papel, nome, endereço permitido, modelo, versão, uptime e fonte quando disponíveis.
- Topologia lógica: WANs → MikroTik → switches/APs → computadores; VLANs/SSID quando conhecidos.
- Conexões confirmadas, informadas manualmente e inferidas devem ter marcadores distintos e data/fonte.
- IP na mesma rede não comprova ligação física direta. Exibir “ligação não confirmada” quando faltar LLDP/controlador/inventário.
- Clique em nó abre detalhe; clique em ligação abre métricas daquele caminho, se coletadas.
- Manter tabela equivalente para leitura sem depender do gráfico ou apenas de cores.

### WANs e MikroTik

No MVP, por WAN: nome/interface reais após inventário, estado observado, origem do estado, probe/saída quando existente e última transição. Não afirmar que cada WAN tem internet só por haver rota ou interface ativa. Tráfego RX/TX, capacidades, perda/latência e uso de link ficam para expansão, conforme a leitura suportada e validada.

**Link físico ativo, rota selecionada e acesso à internet são sinais diferentes.** Reserva não utilizada não significa indisponível. Mostrar histórico de mudanças e degradação. Para CPU/RAM/temperatura/erros de interface, exibir apenas métricas suportadas e frescas.

### UniFi e Wi-Fi

- O U6+ é um AP Wi-Fi; MikroTik continua como gateway no padrão descrito pelo usuário.
- No MVP, mostrar online/sem comunicação/estado desconhecido do U6+ a partir do controller e com horário da observação.
- Estado do controller separado do estado dos APs; indisponibilidade do controller não marca automaticamente AP offline.
- Dispositivos adotados, uplink e clientes associados quando a integração/API suportar; inventário/versão ainda precisam ser confirmados por cliente.
- SSID, banda/canal, sinal, retransmissões e utilização de canal: expansão conforme API/modelo.
- Histórico por AP e comparativo de clientes; sinal Wi-Fi e throughput negociado não equivalem à velocidade da internet.
- Usar nomes técnicos ou identificadores minimizados; não coletar conteúdo de navegação.

### Computadores — etapa posterior

Estado de comunicação do agente, última coleta, tipo de conexão, gateway, latência/perda notebook → gateway e notebook → alvos autorizados. Mostrar cabo/Wi-Fi/SSID apenas quando informado pelo sensor.

Notebook desligado, suspenso ou fora da unidade pode ficar sem comunicação; não concluir quebra da rede. Registrar janela esperada de uso. CPU, RAM, disco e serviços locais entram em expansão; temperatura somente se suportada.

## 4. Histórico e análise

- Períodos: última hora, 24 h, 7 dias e intervalo personalizado, respeitando retenção.
- Curvas de RTT mediano/p95, perda, variação de RTT, tráfego e utilização; unidade e origem visíveis.
- Sobrepor eventos: perda de coleta, WAN mudou, equipamento reiniciou, manutenção começou.
- Comparar dois dispositivos no mesmo destino e período ou duas WANs com origem/rota comprovadas.
- Mostrar lacunas e dados recebidos com atraso. Não preencher falha de coleta como sucesso.
- Disponibilidade acompanhada de cobertura observada e tempo desconhecido; fórmula em [[02 - Arquitetura/Coleta e significado das métricas]].

## 5. Incidentes e alertas

Abertura → reconhecimento por técnico → investigação → recuperação observada → fechamento. Reconhecer não significa resolver. Registrar responsável, horários, evidências, hipótese, impacto e ações humanas.

Correlacionar falhas de componentes dependentes sob incidente principal, preservando sinais individuais. Se o túnel sumir, abrir “sem comunicação com a unidade/túnel” e marcar dependentes como desconhecidos; não criar dezenas de “equipamento caiu” sem evidência.

No MVP, registrar incidentes no painel e enviar alertas/recuperações ao Telegram interno da equipe HUB. Deduplicar, confirmar falha/recuperação e diferenciar perda de coleta, estado não verificado e falha observada. Canais/destinos de clientes ficam para fase posterior.

## 6. Relatórios e administração

Relatórios por cliente/unidade: disponibilidade com cobertura, recorrências, tempo de indisponibilidade observada, WANs, incidentes e evidências de atendimento. Exportações respeitam permissões e minimização de dados.

Administração: inventário, unidade, capacidade dos links, modalidade de coleta, credenciais de sensores, acesso de técnicos, manutenção, limites e retenção. A primeira entrega não inclui executar comandos arbitrários, trocar WAN ou reiniciar equipamentos pelo painel.

## 7. Fases do produto

| MVP confirmado | Evolução após o piloto |
|---|---|
| Visão geral e detalhe de clientes/unidades para equipe HUB | Portal e contas de clientes |
| MikroTik, estado de cada WAN e U6+ online | Métricas Wi-Fi detalhadas, tráfego e comparações |
| Histórico básico, cobertura/frescor e incidentes | Baselines, relatórios e exportações programadas |
| Alertas no painel e Telegram interno | Computadores, agentes e saúde ampla de endpoints |
| Autenticação e isolamento entre clientes | Topologia automática com fontes e confiança |

Vinculado a [[plano]], [[02 - Arquitetura/Coleta e significado das métricas]] e [[04 - Testes/Plano de aceite]].
