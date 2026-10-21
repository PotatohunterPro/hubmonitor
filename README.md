# HUB Monitoramento

Projeto da central de análise de redes de clientes da HUB. A direção atual é hospedar o endpoint e o painel na VPS e evoluir para uma visão multi-cliente.

## Escopo confirmado do MVP

- Painel de uso interno da equipe HUB.
- Comunicação do MikroTik e estado individual das WANs, somente quando houver uma sonda por link comprovada.
- Estado do UniFi U6+ como access point, separado da disponibilidade do controller.
- Histórico e incidentes no painel, com notificações para o canal interno autorizado do Telegram.
- Computadores e agentes de endpoint ficam para uma etapa posterior.
- WireGuard é a modalidade prioritária de coleta remota sem computador sempre ligado; compatibilidade e autorização precisam ser confirmadas por unidade.
- HUB e UniFi OS Server serão avaliados juntos somente no piloto e após preflight da VPS. Migração dos U6+ existentes será gradual, por cliente.

## Estado atual

A central multi-cliente e a integração UniFi ainda não foram implementadas. O código presente é uma base local anterior, com configuração global de MikroTik e sem isolamento multi-cliente; não deve ser publicado como painel de produção na internet. Esta etapa atualiza planejamento e documentação, sem alterar APIs ou configurar redes.

Palone é apenas candidato a piloto, condicionado à confirmação de acesso e autorização. Inventário, sondas WAN, compatibilidade do RouterOS/controller e recursos da VPS continuam pendentes.

## Vault Obsidian

- [00 - Início](00%20-%20In%C3%ADcio.md) — índice e estado para retomar o projeto.
- [Plano](plano.md) — objetivo, escopo e limites atuais.
- [Painel de análise de rede](01%20-%20Projeto/Painel%20de%20an%C3%A1lise%20de%20rede.md) — requisitos do painel.
- [Visão da arquitetura](02%20-%20Arquitetura/Vis%C3%A3o%20da%20arquitetura.md) — fluxo e modalidades de coleta.
- [Decisões vigentes](02%20-%20Arquitetura/Decis%C3%B5es/Decis%C3%B5es%20vigentes.md) — decisões confirmadas e propostas.
- [Plano e pendências](03%20-%20Planejamento/Plano%20e%20pend%C3%AAncias.md) — sequência de trabalho e lacunas.
- [Plano de aceite](04%20-%20Testes/Plano%20de%20aceite.md) — critérios futuros, ainda não executados.
- [Instalação e segurança](05%20-%20Opera%C3%A7%C3%A3o/Instala%C3%A7%C3%A3o%20e%20seguran%C3%A7a.md) — requisitos de operação e preflight.

## Segurança do repositório

Use `.env.example` somente como modelo. Não versione `.env`, credenciais, chaves privadas, bancos locais, logs, backups, dados de clientes nem estado de janela do Obsidian. Revise qualquer evidência operacional antes de compartilhar.
