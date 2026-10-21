---
tipo: decisoes-pendentes
status: pendente
atualizado: 2026-10-20
tags:
  - hub-monitoramento
---

# Decisões pendentes

## Decisões confirmadas — 20/10/2026

- **Máquina sempre ligada:** depende do cliente; planejar as duas situações.
- **MVP:** painel da equipe HUB; MikroTik, estado individual de WANs, U6+ online, histórico e alertas no painel e Telegram. Computadores ficam para depois.
- **Coleta remota sem PC:** WireGuard prioritário, sem túnel criado ainda.
- **UniFi:** U6+ já estão adotados em controllers existentes; migração gradual por cliente.
- **VPS:** avaliar HUB e UniFi OS Server na mesma VPS apenas no piloto, depois do preflight de OS, recursos, portas, backups e recuperação. Produção não decidida.
- **Palone:** candidato a piloto se acesso e autorização forem confirmados; rede e inventário ainda pendentes.

## Pendências antes de implementar

| ID | Informação / escolha | Recomendação de trabalho | O que depende disso |
|---|---|---|---|
| Q01 | VPS: sistema/arquitetura, CPU, RAM, disco, região, domínio, serviços/portas e backups | Inventariar sem solicitar/armazenar senhas na vault | Aprovar ou reprovar co-hospedagem no piloto e dimensionar |
| Q02 | Acesso, autorização, janela e escala real de Palone | Confirmar responsável e preencher levantamento antes de conectar | Habilitar somente o piloto autorizado |
| Q03 | Modelo/versão RouterOS, WireGuard, roteamento de retorno e sub-redes repetidas | Verificar sem alterar o router | Compatibilidade, isolamento e acesso privado por cliente |
| Q04 | Interfaces reais e probes existentes para cada WAN | Associar probe à saída real; não assumir WAN1/2/3 | Estado por WAN; sem prova, mostrar não verificada |
| Q05 | Tipo/versão do controller UniFi, modelo de cada U6+, backup e permissões | Inventariar por cliente; preservar exceções incompatíveis | API, migração gradual, portas e rollback |
| Q06 | Escala inicial e em 12 meses | Medir clientes/unidades, routers, APs, WANs e frequência | Banco, recursos, custos e retenção |
| Q07 | Banco central, retenção e agregação | Escolher após carga, volume e restore do piloto | Migração do SQLite e armazenamento |
| Q08 | Intervalos, limiares, janela de manutenção e confirmação de alertas | Calibrar no piloto; Telegram fica interno à HUB no MVP | Reduzir ruído sem ocultar falhas |
| Q09 | Hospedagem UniFi após o piloto | Medir escala/conflitos e decidir separar, manter ou usar hosting oficial | Arquitetura e custo de produção |
| Q10 | Oferta, cobrança e horário de atendimento | Rever depois de conhecer o custo por unidade | Proposta comercial e cobertura |

## Forma de registrar

Para cada nova resposta, registrar data e origem, atualizar [[02 - Arquitetura/Decisões/Decisões vigentes]] e os documentos afetados. Se a decisão estiver parcial, descrever exatamente o que continua aberto. Uma recomendação escrita pelo assistente não é uma aprovação do usuário.

Pode-se continuar refinando a documentação enquanto as informações faltam. Não inventar especificações da VPS, topologia Palone, suporte de APIs ou orçamento.
