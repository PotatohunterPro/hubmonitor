---
tipo: contrato-de-metricas
status: proposta
atualizado: 2026-10-21
tags:
  - hub-monitoramento
---

# Coleta e significado das métricas

> [!important] Regra principal
> Todo número precisa de **origem, destino, método, horário, unidade e qualidade da coleta**. Nenhum valor do exemplo Palone é uma medição real.

## Escopo do MVP confirmado

O MVP acompanha comunicação do MikroTik, estado individual de cada WAN, estado online do U6+, histórico e alertas para a equipe HUB pelo painel e Telegram. Computadores e medições originadas em notebooks ficam para etapa posterior. “U6+ online” significa AP observado pelo controller; o AP não é o gateway.

## Matriz de coleta

| Exibição desejada | Fonte possível | O que permite concluir / limite |
|---|---|---|
| MikroTik observado | Consulta autenticada recente pela interface/API RouterOS dentro do túnel WireGuard | Prova alcance da gestão pelo túnel, não saúde total da LAN nem encaminhamento fim a fim |
| WAN individual | Sonda Netwatch existente ou teste por link/saída comprovada, associado à interface real | Interface ativa ou ping pela rota padrão não comprova cada WAN; sem teste independente, mostrar **não verificada** |
| U6+ online | Estado do AP obtido no controller UniFi migrado/compatível, com timestamp e frescor | Se o controller/API ficar indisponível, estado do AP é desconhecido/obsoleto, não offline automaticamente |
| Notebook 1 → MikroTik, RTT/perda | Agente futuro no notebook envia sondas ao gateway cadastrado | Caminho observado a partir do notebook; fora do MVP e requer confirmar que está na rede da unidade |
| Coletor → MikroTik/UniFi | Sondas iniciadas em coletor futuro | Alcance desse caminho; não representa a origem notebook ou AP |
| UniFi → MikroTik, RTT/perda | Medição originada no AP ou telemetria específica comprovada | Só habilitar se a capacidade existir. Ping do coletor/VPS recebe seu próprio rótulo |
| Tráfego WAN RX/TX | Contadores de interface obtidos por integração compatível | Taxa calculada por variação de contador; reinício/reset não gera taxa negativa |
| AP online e uplink | Controller/API compatível e acessível pelo plano aprovado | Controller sem acesso torna o estado do AP desconhecido, não offline |
| Sinal, canal e qualidade Wi-Fi | Métricas do controller/dispositivo/agente, conforme suporte | RSSI não é latência e taxa de enlace não é banda disponível |
| CPU, RAM, disco e temperatura | Agente ou API/SNMP compatível | Recursos opcionais; temperatura pode não existir no hardware |
| DNS, TCP/TLS e serviço | Sonda na origem relevante para alvo cadastrado | Conectividade observada; não prova sucesso da aplicação final |
| VPS ↔ cliente | Sonda da VPS via caminho conhecido, se permitido | Caminho externo/VPN, distinto da latência interna da unidade |

## Multi-WAN sem falsa redundância

Cadastrar para cada link: ID, interface/sessão, operadora informada, papel, capacidade contratada e fonte do mapeamento. Não assumir nomes `ether1`/WAN1 nem operadoras do ambiente Bertolo.

Para chamar uma WAN de disponível, separar evidências: físico/sessão, gateway, teste externo por aquela WAN, estado da rota e horário. Uma sonda pela rota padrão pode sair sempre pela WAN ativa e não testa as reservas. Precisamos comprovar caminho de ida/retorno e sondagem por link na configuração real. Quando a coleta atual não permitir isso, mostrar **internet dessa WAN não verificada**.

Leitura de Netwatch existente pode ser fonte, mas exige confirmar destino, origem, roteamento e significado do item. Uma sonda que segue a rota padrão não comprova a WAN de reserva. Criar/alterar sondas, permissões, tabelas, túneis ou rotas é mudança de configuração futura com revisão e autorização próprias; não fazer nesta atualização. Preferir sinais existentes e compatíveis.

Comparar mais de um alvo autorizado ajuda a distinguir falha do destino de falha de acesso, sem atribuir automaticamente culpa à operadora.

## Semântica dos estados

Separar **conectividade**, **saúde**, **cobertura** e **manutenção**.

| Estado | Critério proposto |
|---|---|
| Online / normal | Medições recentes, válidas e critérios obrigatórios do perfil atendidos |
| Degradado | Coleta recente com perda, atraso, saturação ou redundância reduzida persistentes |
| Falha observada | Sensor operacional registra falha repetida de um teste específico; exibir qual teste |
| Sem comunicação | Não chegam contatos no prazo; não comprova causa nem queda de todos os dispositivos |
| Desconhecido | Evidências insuficientes, contraditórias ou dependência sem observação |
| Não suportado | Integração/hardware não fornece a métrica |
| Não monitorado | Sensor ou alvo ainda não configurado |
| Manutenção | Janela registrada; manter estado técnico e histórico, ajustar notificações conforme política |

Uma unidade pode estar **conectada e degradada**, por exemplo WAN principal operante e reserva com falha. Uma unidade com dados de só parte dos equipamentos tem **cobertura parcial**, mesmo que todos os dados recebidos sejam normais.

## Agregação proposta

- Inventário define itens esperados, criticidade e janela de funcionamento; não usar apenas dispositivos que enviaram dados como denominador.
- Túnel WireGuard/coleta sem contato: sensor/unidade sem comunicação ou obsoleta; equipamentos dependentes ficam desconhecidos, mantendo último estado e horário visíveis.
- Coletor operante com falha em uma máquina: incidente localizado.
- WAN com falha e outra funcional: unidade conectada, rede degradada; não rotular loja inteira offline.
- Todos os links falharam segundo sensores locais: registrar observação e horário; se o dado chega só depois, classificar como evento histórico.
- Queda do controller não prova queda do U6+ nem de toda a rede; correlacionar com outras fontes independentes, se existirem.
- Dado reenviado após recuperação não deve disparar alerta atual de queda antiga nem apagar incidente atual.

## Definições numéricas

- **Latência:** RTT em ms, com mediana e p95 sobre respostas válidas em janela definida; timeout é falha, não valor zero.
- **Perda:** sondas enviadas sem resposta no prazo / sondas enviadas × 100, apenas quando o sensor realmente executou a rodada. Coleta ausente entra em cobertura, não em perda ICMP.
- **Variação de RTT:** média de `abs(RTT atual - RTT anterior)` entre respostas consecutivas válidas da mesma janela; não atravessar lacunas. Rotular “variação de RTT”, sem prometer medição de jitter unidirecional.
- **Tráfego:** diferença de bytes entre amostras válidas × 8 / segundos. Tratar reinício/overflow/reset. Exibir bit/s, não confundir com bytes/s.
- **Utilização:** taxa / capacidade configurada × 100. Distinguir capacidade física da porta e velocidade contratada do link. Sem denominador conhecido, mostrar taxa e utilização indisponível.
- **Disponibilidade observada:** tempo com teste classificado como sucesso / (tempo com sucesso + tempo com falha) × 100, limitado ao período/janela elegível. “Degradado” conta conforme o teste específico, não arbitrariamente.
- **Cobertura:** tempo com evidência válida / tempo elegível × 100; sempre publicar junto da disponibilidade e do tempo desconhecido. Manutenção excluída deve ser explícita no relatório.
- Converter amostras em duração com validade limitada pelo TTL do teste; não estender último sucesso através de horas sem dados. Períodos sem base suficiente ficam “sem amostras”.

## Cadência inicial para dimensionamento — proposta a calibrar

| Coleta | Referência inicial |
|---|---|
| Sondas leves de conectividade | Rodada a cada 15 s; quantidade e timeout a fechar no piloto |
| Heartbeat e envio de lotes | A cada 30 s, com variação para evitar rajadas |
| Contadores/recursos de equipamentos | A cada 60 s |
| Inventário e versões | A cada 6 h ou alteração detectada |
| Sem comunicação | Exemplo: 3 heartbeats ausentes mais tolerância de transporte definida |
| Falha/recuperação | Exemplo: 3 rodadas com falha para abrir; 2 saudáveis para recuperar |

Valores não são SLA nem alteração do código. Usar TTL por fonte. Calibrar limiares por LAN cabeada, Wi-Fi, WAN e equipamento. Definir baseline antes de rotular um valor como 20 ms de problema.

Para retenção, avaliar 7 dias de amostras detalhadas, 90 dias de agregados de 5 minutos e 12 meses de incidentes; proposta sujeita a custo e necessidade. Estimar amostras/dia por sensor (86.400 / intervalo × séries), armazenamento, índices, backup e crescimento antes de dimensionar VPS.

## Qualidade e privacidade

Guardar horário de medição e recebimento em UTC; exibir no fuso escolhido. Identificar relógio fora de sincronia, duplicatas, atraso e lacunas. Falhas de credencial, timeout e capacidade não suportada devem ser erros diferentes.

Não coletar conteúdo de pacotes, senhas Wi-Fi, navegação, XML ou dados de cartão. Destinos e inventário devem ser autorizados; descoberta e diagnóstico sob demanda precisam de escopo e limites próprios.

Fontes: [[06 - Referências/Mapa de fontes]], requisitos desta conversa e propostas de modelagem desta nota. Capacidades reais dependem do levantamento.
