"""Alertas e resumos operacionais do serviço HUB Monitoramento.

Principios:
  - o Telegram NAO substitui o dashboard;
  - enviar incidente confirmado, recuperacao, falha do proprio monitor e
    resumo diario, habilitado por padrao para o serviço;
  - nunca repetir a mesma falha enquanto o incidente estiver aberto.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

import httpx

from server.config import ServerSettings
from server.services import diagnostics as diag
from shared import constants as C
from shared.timeutil import format_duration, format_local, utc_now

OK_ICON = "\u2705"
FAIL_ICON = "\u274c"
UNKNOWN_ICON = "\u2754"
ALERT_ICON = "\U0001f6a8"
RECOVER_ICON = "\u2705"
CHART_ICON = "\U0001f4ca"
INFO_ICON = "\U0001f4cb"

CHECK_COMPONENTS = (
    C.COMPONENT_GATEWAY,
    C.COMPONENT_SERVER,
    C.COMPONENT_INTERNET,
    C.COMPONENT_DNS,
    C.COMPONENT_SEFAZ_TCP,
    C.COMPONENT_SEFAZ_TLS,
)


class TelegramNotifier:
    def __init__(self, settings: ServerSettings, http: httpx.AsyncClient, logger: logging.Logger | None = None) -> None:
        self.settings = settings
        self.http = http
        self.log = logger or logging.getLogger("server.telegram")

    @property
    def enabled(self) -> bool:
        return bool(self.settings.telegram_enabled)

    @property
    def api_url(self) -> str:
        return f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"

    async def send(self, text: str) -> bool:
        if not self.enabled:
            return False
        try:
            response = await self.http.post(
                self.api_url,
                json={
                    "chat_id": self.settings.telegram_chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
                timeout=15.0,
            )
        except Exception as exc:  # noqa: BLE001
            # O token faz parte da URL do Bot API e pode aparecer em mensagens
            # de excecao HTTP; registre somente o tipo para nunca vaza-lo.
            self.log.warning("Falha ao enviar mensagem no Telegram (%s)", type(exc).__name__)
            return False

        if response.status_code >= 400:
            self.log.warning("Telegram respondeu HTTP %s ao enviar mensagem", response.status_code)
            return False
        return True

    # ------------------------------------------------------------------
    def format_incident(
        self, incident: Mapping[str, Any], statuses: Mapping[str, Mapping[str, Any]]
    ) -> str:
        component = str(incident.get("type"))
        label = C.COMPONENT_LABELS.get(component, component)
        affected = list(incident.get("affected_machines") or [])
        diagnostic_text = incident.get("diagnosis") or "Analise em andamento."
        active_wan = incident.get("active_wan")

        lines = [
            f"{ALERT_ICON} HUB Monitor | Sinal de atenção",
            f"Loja: {self.settings.store_name}",
            f"Indício: {label}",
            "",
            "Caixas afetados:",
            *affected,
            "",
            "Verificações:",
        ]
        for item in CHECK_COMPONENTS:
            if item == component:
                continue
            lines.append(f"{C.COMPONENT_LABELS.get(item, item)}: {self._icon(statuses, affected, item)}")
        lines.append(f"{C.COMPONENT_LABELS.get(component, component)}: {FAIL_ICON}")
        lines.append("")

        # Texto exigido pelo pedido: o teste TCP/TLS nao comprova
        # autorizacao fiscal, entao a mensagem nao pode sugerir isso.
        if component in (C.COMPONENT_SEFAZ_TCP, C.COMPONENT_SEFAZ_TLS):
            lines += ["Acesso à SEFAZ indisponível nesta loja.", ""]

        if active_wan:
            lines += ["Link identificado:", str(active_wan), ""]

        lines += [
            "Leitura automática (hipótese, requer confirmação):",
            diagnostic_text,
            "",
            "A leitura indica onde os testes encontraram o problema; não confirma a causa final.",
            "A análise humana da HUB segue o horário comercial do serviço.",
            "",
            "Início:",
            format_local(incident.get("started_at"), "%H:%M:%S"),
        ]
        return "\n".join(lines)

    def format_recovery(self, incident: Mapping[str, Any]) -> str:
        component = str(incident.get("type"))
        label = C.COMPONENT_LABELS.get(component, component)
        affected = list(incident.get("affected_machines") or [])
        return "\n".join(
            [
                f"{RECOVER_ICON} HUB Monitor | Sinal normalizado",
                f"Loja: {self.settings.store_name}",
                f"Item: {label}",
                "",
                "Caixas afetados:",
                *affected,
                "",
                "Início:",
                format_local(incident.get("started_at"), "%H:%M:%S"),
                "",
                "Normalização:",
                format_local(incident.get("recovered_at"), "%H:%M:%S"),
                "",
                "Duração observada:",
                format_duration(incident.get("duration_seconds")),
                *(
                    ["", "Períodos sem observação:", format_duration(incident.get("unobserved_seconds"))]
                    if (incident.get("unobserved_seconds") or 0) > 0
                    else []
                ),
                "",
                "O teste voltou a responder normalmente.",
            ]
        )

    def format_retrospective(self, incident: Mapping[str, Any]) -> str:
        """Resumo unico de uma ocorrencia encerrada antes do aviso.

        Usado quando a falha comecou e terminou durante a perda de
        comunicacao: nao anunciamos uma falha antiga como se fosse atual.
        """
        component = str(incident.get("type"))
        label = C.COMPONENT_LABELS.get(component, component)
        affected = list(incident.get("affected_machines") or [])
        observed = incident.get("observed_duration_seconds")
        if observed is None:
            observed = incident.get("duration_seconds")
        gap = incident.get("unobserved_seconds") or 0

        lines = [
            f"{INFO_ICON} HUB Monitor | Ocorrência já encerrada",
            f"Loja: {self.settings.store_name}",
            f"Item: {label}",
            "",
            "Caixas afetados:",
            *affected,
            "",
            "Primeira falha observada: "
            + format_local(incident.get("first_fail_at") or incident.get("started_at")),
            "Confirmação: " + format_local(incident.get("confirmed_at") or incident.get("started_at")),
            "Normalização: " + format_local(incident.get("recovered_at")),
            "Duração observada: " + format_duration(observed),
        ]
        if gap:
            lines.append("Períodos sem observação: " + format_duration(gap))
        if component in (C.COMPONENT_SEFAZ_TCP, C.COMPONENT_SEFAZ_TLS):
            lines += ["", "Acesso à SEFAZ indisponível nesta loja no período acima."]
        lines += [
            "",
            "A ocorrência terminou antes de a comunicação ser restabelecida.",
            "Enviada como resumo: nenhuma ação imediata é necessária.",
        ]
        return "\n".join(lines)

    def format_wan_down(self, alert: Mapping[str, Any]) -> str:
        lines = [
            f"{ALERT_ICON} HUB Monitor | Falha detectada em um link",
            f"Loja: {self.settings.store_name}",
            f"Link monitorado: {alert.get('wan_name')} — {alert.get('provider')}",
            "Evento: falha confirmada no teste do link",
            "",
            "Primeira falha observada: "
            + format_local(alert.get("first_fail_at")),
            "Queda confirmada: " + format_local(alert.get("down_confirmed_at")),
        ]
        if alert.get("probe"):
            lines.append("Alvo do teste: " + str(alert.get("probe")))
        if alert.get("active_route") is True or alert.get("active_route") == 1:
            lines.append("Este link aparece como rota ativa no roteador.")
        lines += [
            "",
            "O teste indica falha no caminho deste link, mas não confirma a causa.",
            "A queda de um link, isoladamente, não confirma queda total da internet da loja.",
        ]
        return "\n".join(lines)

    def format_wan_recovery(self, alert: Mapping[str, Any]) -> str:
        lines = [
            f"{RECOVER_ICON} HUB Monitor | Link normalizado",
            f"Loja: {self.settings.store_name}",
            f"Link monitorado: {alert.get('wan_name')} — {alert.get('provider')}",
            "",
            "Primeira falha observada: " + format_local(alert.get("first_fail_at")),
            "Primeiro retorno observado: " + format_local(alert.get("recovered_at")),
            "Duração observada: " + format_duration(alert.get("duration_seconds")),
            "Confirmação do retorno: " + format_local(alert.get("recovery_confirmed_at")),
        ]
        if alert.get("probe"):
            lines.append("Alvo do teste: " + str(alert.get("probe")))
        lines.append("O teste do link voltou a responder normalmente.")
        return "\n".join(lines)

    def format_wan_retrospective(self, alert: Mapping[str, Any]) -> str:
        lines = [
            f"{INFO_ICON} HUB Monitor | Ocorrência de link já encerrada",
            f"Loja: {self.settings.store_name}",
            f"Link monitorado: {alert.get('wan_name')} — {alert.get('provider')}",
            "",
            "Primeira falha observada: " + format_local(alert.get("first_fail_at")),
            "Queda confirmada: " + format_local(alert.get("down_confirmed_at")),
            "Primeiro retorno observado: " + format_local(alert.get("recovered_at")),
            "Duração observada: " + format_duration(alert.get("duration_seconds")),
            "",
            "A falha e a recuperação foram registradas antes do envio do alerta.",
        ]
        if alert.get("probe"):
            lines.insert(-1, "Alvo do teste: " + str(alert.get("probe")))
        return "\n".join(lines)

    def format_monitor_failure(self, message: str) -> str:
        return "\n".join(
            [
                f"{ALERT_ICON} HUB Monitor | Agente sem comunicação",
                f"Loja: {self.settings.store_name}",
                "",
                message,
                "",
                "A falta de dados não significa que o caixa esteja normal.",
            ]
        )

    def format_daily_summary(
        self,
        availability: Mapping[str, Mapping[str, float]],
        wan_statuses: Sequence[Mapping[str, Any]],
        incidents: Sequence[Mapping[str, Any]],
        machines: Sequence[str],
    ) -> str:
        lines = [
            f"{CHART_ICON} HUB Monitor | Resumo das últimas 24 horas",
            f"Loja: {self.settings.store_name}",
            f"Caixas acompanhados: {len(machines)}",
            "",
            "Disponibilidade observada:",
        ]

        for component, key in (
            (C.COMPONENT_SEFAZ_TCP, "sefaz_tcp_ok"),
            (C.COMPONENT_INTERNET, "internet_ok"),
        ):
            values = [item.get(key) for item in availability.values() if item.get(key) is not None]
            if values:
                average = sum(values) / len(values)
                lines.append(f"{C.COMPONENT_LABELS.get(component, component)}: {average:.2f}%")
        if not any(item.get(key) is not None for key in ("sefaz_tcp_ok", "internet_ok") for item in availability.values()):
            lines.append("Sem dados suficientes para calcular a disponibilidade.")
        lines.append("")

        if wan_statuses:
            lines.append("Mudanças observadas nos links de internet:")
            for item in wan_statuses:
                previous = item.get("previous_status", "?")
                current = item.get("status", "?")
                lines.append(
                    f"  {format_local(item.get('timestamp'), '%H:%M')} "
                    f"{item.get('wan_name')} {item.get('provider')}: {previous} -> {current}"
                )
            lines.append("")

        lines.append(f"Ocorrências registradas: {len(incidents)}")
        if incidents:
            longest = max(incidents, key=lambda item: item.get("duration_seconds") or 0)
            lines.append(
                "Maior ocorrência: "
                f"{C.COMPONENT_LABELS.get(str(longest.get('type')), longest.get('type'))} - "
                f"{format_duration(longest.get('duration_seconds'))}"
            )

        counts: dict[str, int] = {}
        for incident in incidents:
            for machine in incident.get("affected_machines") or []:
                counts[machine] = counts.get(machine, 0) + 1
        if counts:
            worst = max(counts.items(), key=lambda item: item[1])
            lines += ["", "Caixa com mais ocorrências:", f"{worst[0]} ({worst[1]})"]

        if machines and not incidents:
            lines += ["", "Nenhuma ocorrência registrada no período."]
        elif not machines:
            lines += ["", "Nenhum caixa enviou dados no período; disponibilidade não pode ser confirmada."]

        lines += [
            "",
            "Os percentuais representam os testes do monitor e não confirmam a causa de falhas externas.",
            f"Gerado em {format_local(utc_now())}",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    @staticmethod
    def _icon(statuses: Mapping[str, Mapping[str, Any]], affected: Sequence[str], component: str) -> str:
        values = [diag.component_status(statuses.get(machine, {}), component) for machine in affected]
        values = [value for value in values if value is not None]
        if not values:
            return UNKNOWN_ICON
        if all(values):
            return OK_ICON
        return FAIL_ICON
