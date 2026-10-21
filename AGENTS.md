# Orientação de trabalho — HUB Monitoramento

Antes de trabalhar neste projeto:

1. Leia [[00 - Início]], [[01 - Projeto/Contexto para agentes]] e [[plano]].
2. Consulte [[06 - Referências/Mapa de fontes]] e leia os documentos/código relevantes à tarefa.
3. Confirme no checkout o estado atual de artefatos, testes e integrações antes de afirmar que algo está pronto ou validado.

## Direção vigente — registrada em 20/10/2026

- O alvo é endpoint e dashboard na VPS, com análise da rede de múltiplos clientes, MikroTik, WANs, UniFi e computadores.
- Prever clientes com e sem computador sempre ligado, conforme requisito confirmado pelo usuário.
- MVP confirmado: painel da equipe HUB com MikroTik, estado individual de cada WAN, U6+ online, histórico e alertas no painel e Telegram. Computadores ficam para a etapa seguinte.
- No padrão informado, o MikroTik é o gateway e o UniFi U6+ é o ponto de acesso Wi-Fi. Não tratar o U6+ como roteador.
- WireGuard é a modalidade prioritária para coleta remota quando não houver computador ligado; compatibilidade, rotas e autorização devem ser verificadas antes de qualquer configuração. Não abrir gestão pública como fallback automático.
- Dashboard do MVP restrito à equipe HUB. UniFi OS Server e HUB podem compartilhar a VPS apenas no piloto, após preflight de compatibilidade, recursos, portas, backups e recuperação; a topologia de produção continua pendente.
- Os U6+ já estão adotados em controladores existentes; migração gradual por cliente foi escolhida, mas controladores/modelos/versões ainda precisam ser inventariados. Palone é candidato a piloto somente após confirmação de acesso e autorização.
- A tarefa que estabeleceu a direção central é de planejamento e Markdown. Não implementar, implantar, alterar redes ou testar por inferência; seguir o escopo explícito de cada nova tarefa.
- A base local anterior não comprova implementação da central. Não reintroduzir como atual a antiga decisão de adiar multiempresa.
- Agentes de computador e coletor dedicado ficam como alternativas futuras; consulte [[02 - Arquitetura/Decisões/Decisões vigentes]] antes de tratá-los como escolhidos.
- Preserve origem/destino/horário e cobertura das métricas. “Sem comunicação” não comprova queda de toda a rede.
- Ao terminar trabalho significativo, atualize o estado e próximo passo em [[00 - Início]] e [[03 - Planejamento/Plano e pendências]].

## Como interpretar a documentação

- A vault serve como mapa de contexto, decisões e links. Ela não substitui a leitura da fonte original nem comprova o estado ao vivo.
- `plano.md` descreve intenção e escopo; código indica implementação; logs, artefatos e resultados de execução sustentam afirmações de validação.
- Diferencie sempre: **decidido**, **planejado**, **implementado**, **testado** e **validado no ambiente real**.
- Trate `plano_historico.md` e instaladores antigos como histórico, não como instrução para o fluxo vigente.
- Se a documentação parecer desatualizada, confira o código e os artefatos atuais e registre a diferença com data e evidência.

## Regras do projeto

- Responda em português brasileiro e seja direto.
- Não invente resultado, configuração de cliente, preço ou cobertura operacional.
- Em rede ou ambiente de cliente, comece por diagnóstico somente leitura. Preserve configuração, rotas, Netwatch e failover da MikroTik; só proponha mudança após apresentar evidências e obter autorização adequada.
- Não exponha tokens, senhas, chaves privadas, `.env`, dados fiscais ou dados pessoais em notas, respostas ou anexos.
- Respeite pedidos de planejamento apenas: não implemente nem execute validação quando o escopo for somente planejar.
- Depois de uma decisão durável ou validação com evidência, atualize a nota pertinente na vault e aponte a fonte.
