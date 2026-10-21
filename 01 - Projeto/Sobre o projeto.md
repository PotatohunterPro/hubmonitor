---
tipo: projeto
status: planejado
atualizado: 2026-10-20
aliases:
  - Sobre
  - Visão do produto
tags:
  - hub-monitoramento
---

# Sobre o projeto — HUB Monitoramento

## Definição

**Uma central da HUB para acompanhar e analisar as redes dos clientes, hospedada na VPS do usuário.**

A equipe abre o painel, vê quais clientes precisam de atenção e entra na unidade para consultar roteador, links de internet, UniFi e computadores. Cada sinal tem origem, destino, horário e histórico para apoiar o diagnóstico.

## Problemas que o painel deve ajudar a investigar

- A lentidão está restrita a um notebook ou afeta vários dispositivos?
- Existe evidência de falha na LAN, no Wi-Fi ou em uma WAN específica?
- O equipamento responde, mas a aplicação ou DNS falha?
- O link reserva continua disponível enquanto o principal está ativo?
- O coletor deixou de comunicar ou há falha observada no equipamento?
- A falha é nova, recorrente ou coincide com troca de WAN/manutenção?

As respostas são evidências e hipóteses; a causa final exige confirmação técnica.

## Usuários e organização

- Inicialmente, técnicos e administrador da HUB.
- Cliente → unidade → dispositivos, interfaces, links, agentes e coletores.
- Clientes podem reutilizar IPs privados e nomes de equipamentos; identidade não pode depender só de IP ou hostname.
- Acesso de clientes ao próprio painel: decisão futura, com permissões restritas.
- Prever unidades com computador sempre ligado e unidades sem esse recurso, conforme resposta do usuário em 20/10/2026.

## Visão completa e primeiro recorte

O painel completo está em [[01 - Projeto/Painel de análise de rede]]. A primeira entrega proposta prioriza visão geral, detalhe por cliente, WANs, dispositivos, latência/perda com origem e incidentes básicos. Recursos avançados ficam acompanhados no backlog, sem serem apresentados como disponíveis.

Palone é o exemplo fornecido pelo usuário e candidato a piloto; instalação real e inventário ainda não confirmados.

## O que muda em relação ao projeto anterior

| Antes | Direção atual |
|---|---|
| Primeiro pacote: caixas e conectividade do varejo | Análise de rede de vários clientes |
| Servidor e painel locais por loja | Endpoint e dashboard centralizados na VPS |
| Plataforma multiempresa adiada | Separação por cliente é requisito central |
| Caixa como entidade principal | Cliente, unidade, equipamentos e caminhos |
| Oferta-base de até três caixas | Oferta e limites por unidade/dispositivo a redefinir |

O código anterior é base para avaliar reaproveitamento. O plano novo não prova que a central já exista.

## Apresentação proposta

> O HUB Monitoramento reúne a rede dos seus clientes em um painel central. A equipe acompanha links de internet, equipamentos e qualidade das conexões, consulta o histórico e usa evidências para localizar onde investigar falhas e lentidão.

Fontes: pedido e resposta do usuário em 20/10/2026, [[plano]] e [[02 - Arquitetura/Decisões/ADR-001 - Central na VPS]].
