---
tipo: levantamento
status: pendente
atualizado: 2026-10-20
tags:
  - hub-monitoramento
---

# Levantamento do piloto Palone

> [!warning] Exemplo, não inventário confirmado
> Palone foi citado pelo usuário para explicar o painel. Não foi acessada sua rede. Três WANs, UniFi e Notebook 1 são itens do exemplo a confirmar; 1 ms e 20 ms não são dados coletados.

> [!important] Condição para iniciar
> Palone é apenas candidato. Não conectar, instalar, adotar dispositivos nem coletar dados até confirmar responsável, autorização de acesso e janela. O primeiro levantamento é somente leitura.

## Sequência segura do piloto

1. Confirmar autorização, escopo, responsável, janela e contato para retorno.
2. Fazer inventário somente leitura: modelo/versão RouterOS, interfaces e WANs reais, sondas já existentes, U6+, tipo/versão/local do controller, topologia mínima e recursos/serviços existentes na VPS.
3. Concluir o preflight da VPS: sistema operacional compatível com a versão atual do UniFi OS Server; CPU, memória e armazenamento disponíveis; portas e serviços em uso; backups existentes e procedimento de recuperação. Registrar evidências sem credenciais.
4. Se houver incompatibilidade, conflito ou recuperação insuficiente, interromper a co-hospedagem antes de instalar e registrar alternativas para decisão. Não abrir a gestão do MikroTik publicamente como fallback.
5. Antes de cada migração UniFi por cliente, gerar e conferir backup do controller atual. Migrar gradualmente e confirmar o U6+ online no controller novo e a operação Wi-Fi antes de retirar o antigo.
6. No aceite futuro, verificar isolamento entre dois clientes de teste e simular indisponibilidade do túnel e do controller. Falha de coleta deve aparecer como sem comunicação/estado desconhecido ou obsoleto, sem declarar toda a rede ou o AP offline sem evidência independente.

Para adoção remota camada 3, confirmar conectividade de gestão aprovada; o guia oficial indica TCP 8080. Migração deve seguir backup/restauração e verificação por cliente. Consulte [[02 - Arquitetura/Recomendação de hospedagem UniFi]] e [[06 - Referências/Mapa de fontes]].

## Informações pendentes

| Grupo | Preencher sem credenciais |
|---|---|
| Piloto | Confirmar cliente/unidade, responsável, autorização de acesso e coleta, escopo e janela |
| Escala | Quantidade de unidades, roteadores, switches/APs, computadores e WANs |
| MikroTik | Modelo, versão/canal RouterOS, papel, interfaces reais e acesso de leitura disponível |
| WANs | Operadora informada, interface/sessão, gateway, capacidade, principal/reserva/balanceamento e sondas existentes; não criar sondas nesta etapa |
| UniFi | Modelo e quantidade de U6+, controller atual (tipo/versão/local), backup disponível e integração/caminho de gestão possível |
| LAN/Wi-Fi | Sub-redes, VLANs, SSIDs necessários, conexões conhecidas e origem do inventário |
| Computadores | Sistema, janela ligada, cabo/Wi-Fi, mobilidade e possibilidade de agente |
| Coleta | Para o MVP, MikroTik compatível e disponibilidade de WireGuard; computador sempre ligado não é requisito. Agentes ficam para etapa posterior. |
| VPN, se aplicável | RouterOS/modelo, terminador, rotas de ida e volta, redes sobrepostas, alcance e política de acesso; nenhum túnel está configurado |
| Serviços | Alvos DNS/TCP/TLS necessários e permitidos; criticidade |
| Operação | Horários, manutenção, contatos e destino autorizado dos alertas |

## Escopo mínimo do MVP para o levantamento

- Uma unidade autorizada, um MikroTik e WANs reais mapeadas por evidência.
- Um U6+ compatível e seu controller atual, com possibilidade de backup e migração gradual.
- Painel/alertas para a equipe HUB; computadores não fazem parte do primeiro aceite.
- Dois clientes de teste para verificar isolamento antes de qualquer uso com dados reais.
- Indisponibilidade simulada do túnel e do controller, cada uma com interpretação de estado correta.

## Resultado esperado do levantamento

Mapa autorizado da unidade; fonte de cada métrica; cobertura e estados desconhecidos; condição da VPS para o piloto; backups/recuperação; dependências, riscos e critérios de aceite. Informações desconhecidas permanecem pendentes, sem credenciais ou dados desnecessários.

Relacionados: [[03 - Planejamento/Decisões pendentes]], [[02 - Arquitetura/Visão da arquitetura]], [[04 - Testes/Plano de aceite]].
