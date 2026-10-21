---
tipo: contexto-operacional
status: vigente
atualizado: 2026-10-20
aliases:
  - Contexto para assistentes
  - Contexto do projeto
tags:
  - hub-monitoramento
---

# Contexto para agentes

## Leitura obrigatória ao retomar

Esta é a memória resumida para trabalhar no projeto. Leia [[plano]], o [[03 - Planejamento/Plano e pendências|backlog]] e a nota da área antes de editar. As instruções atuais do usuário prevalecem.

## Direção vigente — 20/10/2026

- **HUB Monitoramento:** central de análise de rede de vários clientes, endpoint e dashboard na VPS do usuário.
- **MVP confirmado:** painel autenticado para a equipe HUB, com cliente/unidade → MikroTik → estado individual das WANs e U6+ online → histórico/incidentes; alertas no painel e Telegram. Computadores ficam para etapa posterior.
- No padrão informado pela pessoa usuária, MikroTik é o gateway e U6+ é AP Wi-Fi; não assumir que o U6+ roteia a rede.
- O usuário confirmou que algumas unidades têm máquina sempre ligada e outras não. Planejar ambas as situações.
- Para o MVP sem PC, WireGuard é a modalidade prioritária, ainda não configurada; verificar modelo/versão RouterOS, rotas, redes sobrepostas e autorização. Sem compatibilidade, não publicar a gestão do roteador como fallback automático.
- HUB e UniFi OS Server serão avaliados na mesma VPS para o piloto, condicionado a preflight de sistema operacional, recursos, portas e recuperação. A hospedagem de produção permanece em aberto.
- U6+ já estão adotados em controllers existentes; migrar gradualmente por cliente, após inventário e backup. Palone é candidato apenas se acesso e autorização forem confirmados.
- Esta atualização é documental. **Não implementar, publicar, instalar, mudar rede ou executar testes sem autorização e escopo explícitos.**
- Agentes de computador e coletores dedicados são evolução posterior. Banco, retenção e capacidade final da VPS continuam pendentes.
- Não importar a antiga restrição “multiempresa fora do escopo” para o plano novo. O histórico local está em [[99 - Arquivo/Histórico e conteúdo superado]].

## O que está confirmado e o que falta

| Tema | Evidência / estado |
|---|---|
| Mudança de produto e VPS | Pedido do usuário nesta conversa, 20/10/2026. |
| Dois perfis de implantação | Resposta do usuário: “Depende do cliente; precisamos prever as duas situações”. |
| MVP sem computadores | Resposta do usuário em 20/10/2026: MikroTik, estado de cada WAN, U6+ online, histórico/alertas; computadores depois. |
| Coleta por WireGuard | Preferência confirmada pelo usuário em 20/10/2026; compatibilidade e configuração ainda pendentes. |
| Acesso e alertas | Painel somente para equipe HUB; painel e Telegram, respostas do usuário em 20/10/2026. |
| UniFi | U6+ existentes já adotados em controllers atuais; migração gradual por cliente escolhida. Tipo/versão e integração ainda não inventariados. |
| Piloto | Palone é candidato se acesso e autorização forem confirmados; ainda sem inventário/validação. |
| Co-hospedagem | HUB e UniFi OS Server na mesma VPS para avaliar no piloto após preflight; produção não decidida. |
| Palone, três WANs, UniFi e Notebook 1 | Os três WANs e Notebook 1 continuam exemplos; não são inventário nem valores medidos. |
| Central implementada | Não foi implementada nesta revisão; docs descrevem o alvo. |
| Base de código | Arquitetura local documentada no README; conferir arquivos relevantes antes de reutilizar. |
| Acesso atual | Leitura de `server/main.py` e `server/api/routes.py`: ingestão e administração têm controles; painel e consultas de monitoramento não exigem sessão nos handlers consultados. Não tratar como pronto para internet. |
| Build antigo | Consulta anterior de 20/10/2026 a `dist/` encontrou pacotes-fonte, sem Setup.exe. Renovar evidência antes de informar situação atual do build. |
| Testes | Nenhum executado nesta revisão. Relatórios antigos não validam a nova arquitetura. |

## Decisões que não devem ser inventadas

- Nunca inferir WAN 1/2/3 a partir de nomes de portas ou assumir operadoras do Bertolo para Palone.
- Não afirmar suporte REST, API UniFi, SNMP, RSSI, temperatura ou sondas por WAN antes de conhecer versão/modelo/controlador/permissões.
- “WAN online” exige evidência por saída/link mapeado; sem sonda independente comprovada, mostrar **não verificada**. Não derivar o estado de todas as WANs de uma rota padrão.
- AP offline e controller indisponível são estados distintos. Se a fonte UniFi não responde, marcar estado do AP como desconhecido/obsoleto, salvo evidência independente.
- `notebook → MikroTik` precisa de uma medição originada no notebook. Ping da VPS, coletor ou roteador não substitui esse caminho.
- “Sem comunicação”, “falha observada”, “degradado”, “não suportado” e “não monitorado” são estados distintos.
- Ausência de coleta não é zero de latência nem disponibilidade confirmada.
- Não assumir preço, SLA, atendimento 24/7 ou piloto instalado. A oferta anterior está em revisão.

## Fontes por tarefa

| Tarefa | Começar por |
|---|---|
| Produto e UX | [[01 - Projeto/Painel de análise de rede]] |
| Coleta, modelo de dados e integrações | [[02 - Arquitetura/Visão da arquitetura]] e [[02 - Arquitetura/Coleta e significado das métricas]] |
| Decisões e sequência | [[02 - Arquitetura/Decisões/Decisões vigentes]] e [[03 - Planejamento/Decisões pendentes]] |
| Piloto | [[05 - Operação/Levantamento do piloto Palone]] |
| Segurança/operação | [[05 - Operação/Instalação e segurança]] |
| Aceite | [[04 - Testes/Plano de aceite]]; roteiro Bertolo somente como referência anterior |
| Estado da implementação | Código atual, README com ressalvas, logs e artefatos datados |

## Protocolo de memória

1. Diferencie **direção confirmada**, **proposta**, **implementado**, **testado** e **validado no cliente**.
2. Quando o usuário decidir, atualize o registro de decisões e retire a pendência correspondente; registre fonte e data.
3. Ao encerrar trabalho significativo, atualize “Onde paramos” no início e o próximo passo no backlog.
4. Se houver divergência, confira instrução mais recente e evidência atual; não propague automaticamente nota antiga.
5. Preserve histórico e sanitize evidências. Não gravar credenciais, `.env`, dados fiscais ou pessoais.
