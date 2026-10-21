---
tipo: operacao
status: planejado
atualizado: 2026-10-20
aliases:
  - Operação
  - Instalação
tags:
  - hub-monitoramento
---

# Operação e segurança da central

## Estado e fronteiras

Este é o plano operacional da arquitetura-alvo. Não é um guia de deploy pronto para executar. Sistema/recursos da VPS, domínio, implementação e modalidades de coleta ainda precisam ser definidos.

O [[docs/GUIA_INSTALACAO]] descreve a versão local anterior. As rotas administrativas existentes não equivalem a proteção de todas as consultas do painel. Não publicar a aplicação local atual diretamente na internet.

## Preflight da VPS para o piloto

HUB e UniFi OS Server serão avaliados na mesma VPS apenas para o piloto. Antes de instalar qualquer componente, registrar:

- Distribuição e versão do sistema operacional e compatibilidade com a versão vigente do UniFi OS Server.
- CPU e memória disponíveis sob carga normal e espaço livre/total de armazenamento, incluindo crescimento, banco e backups.
- Portas em uso, serviços existentes, regras de firewall, endereços e conflitos com os serviços que o piloto exigiria.
- Estado e localização dos backups atuais da VPS; procedimento de restauração e recuperação comprovado/documentado.
- Responsável, janela autorizada, plano de retorno e evidência sanitizada do levantamento.

Se qualquer requisito for incompatível ou permanecer sem resposta, interromper a co-hospedagem antes da instalação e apresentar alternativas para nova decisão. Não redimensionar, contratar outra VPS nem instalar em outro host por inferência. Esta revisão não executou preflight.

Para a migração de cada cliente UniFi, fazer backup do controller atual antes de iniciar; restaurar/importar no destino, verificar o U6+ online e o funcionamento do Wi-Fi e somente então retirar o controller antigo. A adoção camada 3 requer conectividade aprovada, incluindo TCP 8080 conforme a documentação oficial. Confirmar também as demais portas necessárias na fonte oficial vigente e no firewall real; não abrir portas sem autorização.

## Entrada e acesso na VPS — requisitos

- HTTPS com certificado validado para sensores e usuários; expiração e renovação acompanhadas.
- Login para painel, sessões protegidas, autorização por cliente/unidade e perfis mínimos. Avaliar MFA para administradores.
- Ingestão separada de administração e consulta; credencial individual por coletor/agente, vinculada ao escopo no servidor, revogável e rotacionável.
- Limites de tamanho, taxa e tempo; validação de payload; proteção contra sensor sobrecarregar a central ou outro cliente.
- Banco, filas e gerenciamento acessíveis apenas pelos componentes autorizados. Health público mínimo; diagnósticos detalhados restritos.
- Logs e auditoria sem tokens, senhas ou conteúdo sensível; registrar logins, mudanças, acessos administrativos e ações sobre incidentes.
- Negar acesso entre clientes em todas as camadas, incluindo relatórios, caches e notificações. A UI escondendo uma opção não substitui autorização no servidor.

## Coleta nas unidades

- Modalidade A: usar máquina existente com disponibilidade acordada. Modalidade B: definir coletor dedicado, energia, manutenção e troca. Modalidade C: VPN terminada em equipamento sempre ligado, com isolamento e rotas aprovados.
- No fluxo recomendado, sensor inicia conexão HTTPS para a VPS. Não publicar WinBox, REST, SNMP ou controlador na internet para simplificar a coleta.
- Credenciais de equipamentos com menor privilégio possível; preservar rotas, Netwatch e failover. Leitura de estado e execução de sondas têm permissões diferentes a confirmar.
- Preferir guardar segredo do equipamento junto ao coletor que o utiliza, em armazenamento protegido. Se coleta for central via VPN, guardar segredo na central com escopo e controle de acesso. Nunca na vault ou nos logs.
- Cadastrar alvos de diagnóstico e limitar protocolos/frequência. Descoberta não deve varrer redes de clientes sem escopo autorizado.
- Fila limitada e política explícita de expiração/descarte, reenvio com backoff e prioridade para dados recentes. Mostrar lacunas quando o limite impedir conservar tudo.

## Onboarding proposto

1. Levantar unidade, ativos, topologia, WANs, controller UniFi, janelas e autorização de coleta.
2. Selecionar modalidade e declarar métricas cobertas, indisponíveis e não suportadas.
3. Criar cliente/unidade e identidades no sistema futuro; associar cada sensor sem confiar só no nome/IP. Antes do uso real, comprovar que dados de dois clientes não se misturam.
4. Instalar/configurar em janela acordada, com credenciais restritas e plano de retorno.
5. Validar caminhos, horários e separação de dados conforme [[04 - Testes/Plano de aceite]].
6. Registrar evidência, responsável, limites e contatos; só então ativar notificações reais autorizadas.

## Continuidade da central

- Monitorar ingestão, atraso, filas, CPU/RAM/disco, erros, certificados e falha das notificações.
- Prever observação externa à própria VPS, porque um servidor caído não consegue avisar sobre si mesmo.
- Backup criptografado fora da VPS, retenção e restauração periódica em ambiente separado; definir RPO/RTO antes de prometer prazo.
- Definir atualização, migração de banco, rollback e compatibilidade de versões de sensor.
- Uma VPS única é ponto único de falha; disponibilidade exigida e custo de redundância são decisões futuras.
- Manutenção com início/fim e responsável; registrar estado real mesmo quando notificações estiverem silenciadas.

## Encerramento de cliente ou troca de equipamento

Revogar credenciais, retirar permissões/túneis de forma autorizada, encerrar destinos de notificações, preservar auditoria conforme retenção acordada e definir exportação/eliminação de dados. Não reutilizar identidade de equipamento removido para outro sem histórico.

## Oferta e custos

Dimensionar custo de VPS, armazenamento, backups, eventual coletor dedicado e horas de suporte por unidade. Não assumir preço anterior de três caixas nem atendimento humano 24/7. [[OFERTA_HUB_MONITOR]] é rascunho em revisão.
