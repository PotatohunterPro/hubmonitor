---
tipo: tecnologias
status: documentado
atualizado: 2026-10-20
aliases:
  - Tecnologias
  - Stack
tags:
  - hub-monitoramento
---

# Stack atual e opções para a central

## Base existente — contexto de implementação

| Área | Tecnologia documentada | Fonte |
|---|---|---|
| Agente | Python e fila local SQLite | `agent/`, `agent/queue/local_queue.py` |
| API | FastAPI e Uvicorn | `server/main.py`, `requirements-server.txt` |
| Dados | SQLite e schemas Pydantic | `server/database/db.py`, `shared/schemas.py` |
| Transporte | HTTPS/TLS, token de ingestão | `agent/sender.py`, `server/tls.py`, `server/main.py` |
| Interface | Dashboard web local e interface desktop | `server/dashboard/`, `desktop/` |
| Integrações | Telegram e MikroTik opcionais | `server/services/telegram.py`, `server/services/mikrotik.py` |
| Acesso administrativo | Autenticação de administração existente | `server/services/admin_auth.py`, `server/api/routes.py` |
| Distribuição | PyInstaller e NSIS, scripts Windows | `packaging/`, [[packaging/THIRD-PARTY]] |

Essa tabela orienta inspeção e reaproveitamento. Não comprova execução nem suporte à nova arquitetura.

## UniFi na VPS — proposta condicional

Para autohospedar, avaliar o UniFi OS Server atual, não iniciar com o legado UniFi Network Server. A documentação Ubiquiti lista Ubuntu 24.04+/Debian 13+ para Linux e exige serviços no host; não é um container genérico. Mínimos oficiais do controller não dimensionam o monitor HUB. Ver decisão e portas em [[02 - Arquitetura/Recomendação de hospedagem UniFi]].

## Candidatos para a VPS — não escolhidos

| Área | Recomendação a avaliar | Motivo e condição |
|---|---|---|
| Backend/coletor | Reaproveitar Python/FastAPI onde adequado | Reduzir reescrita; revisar modelo de identidade e responsabilidades |
| Banco central | PostgreSQL candidato | Avaliar volume, isolamento, índices, manutenção e migração antes de decidir |
| Fila do sensor | SQLite local | Reaproveitar comportamento existente após revisar limites e recuperação |
| Dashboard | Escolher evolução da interface existente ou frontend dedicado | Decidir pela UX, gráficos, manutenção e acesso; nenhum framework aprovado |
| HTTPS/publicação | Proxy reverso e certificados gerenciados | Escolher após conhecer sistema, domínio e forma de operação da VPS |
| Execução | Serviços ou containers | Escolha pendente; não pressupor Docker instalado |
| Notificações | Avaliar Telegram existente | Rever destinos por cliente e fila de entrega |
| Conectores | RouterOS REST/API/SNMP e API UniFi conforme ambiente | Confirmar versão, controller, permissões e métricas reais |

Não instalar dependências nem substituir o banco nesta etapa. Especificação de coleta em [[02 - Arquitetura/Coleta e significado das métricas]]; referências oficiais em [[06 - Referências/Mapa de fontes]].
