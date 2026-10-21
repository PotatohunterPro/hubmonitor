---
tipo: testes
status: nao-executado
atualizado: 2026-10-20
aliases:
  - Aceite
  - Testes de campo
tags:
  - hub-monitoramento
---

# Plano de aceite — central na VPS

> [!important] Roteiro futuro
> Nenhum cenário abaixo foi executado nesta revisão. O usuário pediu somente planejamento e Markdown. Executar testes e intervenções de rede somente em etapa autorizada, com janela e ambiente definidos.

## Critérios propostos

Todos os cenários começam como **não executado**. Aplicabilidade depende da modalidade selecionada; justificar “não aplicável” sem anunciar suporte àquela modalidade.

| ID | Cenário | Aceite esperado |
|---|---|---|
| V01 | Cliente → unidade → equipamento/WAN | Navegação consistente, dados do escopo correto e atualização visível |
| V02 | Cliente A e B com mesmo IP/hostname | IDs, consultas, histórico, incidentes, caches e exportações não se misturam |
| V03 | Usuário sem sessão ou sem permissão | Dados/ações protegidos, inclusive APIs, downloads e acesso direto por ID |
| V04 | Credencial de sensor inválida/revogada ou escopo forjado | Ingestão recusada; payload não muda cliente/unidade autorizado |
| V05 | Notebook → gateway versus coletor/VPS → gateway | Origem, destino, horário, RTT e perda correspondem ao sensor real |
| V06 | WAN principal ativa e reserva sem uso | Reserva não é marcada falha por ausência de tráfego; teste independente comprova saída ou sinaliza não verificada |
| V07 | Uma WAN falha e outra funciona | Unidade conectada/degradada, link e período corretos; sem concluir queda total |
| V08 | Coletor desligado ou sem conexão | Unidade sem comunicação, dependentes desconhecidos e última evidência visível; sem tempestade de falsas quedas |
| V09 | Notebook suspenso, desligado ou fora da unidade | Estado respeita janela esperada e localização; não atribui falha à LAN sem evidência |
| V10 | Controlador UniFi indisponível | Estado da fonte/controller distinto do AP; U6+ fica desconhecido/obsoleto sem observação própria, sem ser marcado offline automaticamente |
| V11 | Métrica não suportada/não configurada | Estado explícito, sem zero artificial nem indicador verde |
| V12 | VPS/HTTPS/banco indisponível | Coletor conserva dados dentro de limites; painel sinaliza falta de atualização; observador externo identifica falha da central |
| V13 | Retorno, duplicatas, dados fora de ordem e relógio incorreto | Histórico preserva horário original, deduplica e não reabre queda antiga como atual |
| V14 | Fila cheia e disco limitado | Política de descarte/expiração documentada, lacunas visíveis e sem crescimento ilimitado |
| V15 | Incidente no painel e alerta Telegram interno | Equipe HUB recebe falha/recuperação corretas, sem duplicação; manutenção silencia conforme prazo e preserva estado |
| V16 | Incidente reconhecido | Responsável/auditoria registrados; reconhecimento não implica recuperação |
| V17 | MVP sem computador sempre ligado | WireGuard consulta o MikroTik e a fonte UniFi dentro da cobertura aprovada; nenhuma métrica de notebook é inferida |
| V18 | VPN/WireGuard com clientes em sub-redes iguais | Peers/endereços de túnel ficam isolados; nenhuma rota sobreposta causa consulta cruzada |
| V19 | Gráficos e disponibilidade com lacunas | Fórmulas, unidades, cobertura, desconhecido e manutenção aparecem corretamente |
| V20 | Contadores reiniciados, flapping e recuperação | Sem taxas negativas/picos artificiais; abertura/recuperação respeitam janelas |
| V21 | Backup e restauração da central | Dados e isolamento recuperados em ambiente separado; tempos/perda medidos |
| V22 | Volume-alvo, retenção e atualização | Medir ingestão, consulta, disco e atraso frente a metas definidas antes da execução |
| V23 | Atualização/remoção/migração de sensor | Identidade estável, credencial revogável, sem duplicidade; retorno documentado |
| V24 | Preflight de HUB + UniFi OS Server na mesma VPS | OS/arquitetura suportados, CPU/RAM/disco, portas/serviços, TLS, backup e restore documentados; reprovação interrompe instalação |
| V25 | Perda do túnel WireGuard | VPS mostra túnel/unidade sem comunicação ou dados obsoletos; não marca automaticamente toda a rede, MikroTik ou U6+ como offline |
| V26 | Migração gradual do controller UniFi por cliente | Backup original restaurável; U6+ aparece online e Wi-Fi é confirmado no controller novo antes de esquecer/desligar o antigo; retorno documentado |
| V27 | WAN sem sonda individual mapeada | Link aparece “não verificada”; rota padrão ou interface ativa não gera falso “WAN online” |
| V28 | Isolamento de API e Telegram HUB-only | Usuário sem sessão não acessa o painel/API; alertas seguem só para o destino interno aprovado, sem cruzamento de clientes |

## Evidência de cada execução

Data/hora/fuso, versão, ambiente, cliente/unidade, sensor/origem, destino/interface, método, pré-condições, resultado esperado/observado e evidência sanitizada. Para falhas induzidas ou migração de controller, registrar autorização, janela, impacto e retorno. O preflight de co-hospedagem é um gate operacional, não prova de teste de carga ou de produção.

Estados de execução: não executado · aprovado · reprovado · bloqueado · não aplicável. Um teste só fica aprovado com evidência, usando [[90 - Modelos/Modelo de registro]].

## Reaproveitamento de testes antigos

[[docs/ROTEIRO_TESTE_BERTOLO]] e cenários WAN C8–C13 pertencem à arquitetura local. Avaliar reaproveitamento, mas eles não comprovam VPS, isolamento entre clientes, UniFi ou modalidade sem PC. [[docs/RELATORIO_ENTREGA]] é relatório histórico, não resultado desta revisão.
