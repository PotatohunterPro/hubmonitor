"""Motor de diagnostico - plano secoes 13, 14 e 30.

A logica aqui e puramente funcional (sem banco, sem rede), o que a
torna trivialmente testavel. Toda a arvore de decisao vem do plano.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from shared import constants as C

# Coluna de medida que representa o estado de cada componente
COMPONENT_STATUS_FIELD: dict[str, str] = {
    C.COMPONENT_GATEWAY: "gateway_ok",
    C.COMPONENT_SERVER: "server_ok",
    C.COMPONENT_INTERNET: "internet_ok",
    C.COMPONENT_DNS: "dns_ok",
    C.COMPONENT_SEFAZ_TCP: "sefaz_tcp_ok",
    C.COMPONENT_SEFAZ_TLS: "sefaz_tls_ok",
}


def component_status(status: Mapping[str, Any], component: str) -> bool | None:
    field = COMPONENT_STATUS_FIELD.get(component)
    if not field:
        return None
    value = status.get(field)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return bool(value)


def machine_diagnosis(status: Mapping[str, Any]) -> str:
    """Diagnostico de UMA maquina, na ordem de causa raiz do plano 14."""
    gateway = component_status(status, C.COMPONENT_GATEWAY)
    server = component_status(status, C.COMPONENT_SERVER)
    internet = component_status(status, C.COMPONENT_INTERNET)
    dns = component_status(status, C.COMPONENT_DNS)
    tcp = component_status(status, C.COMPONENT_SEFAZ_TCP)
    tls = component_status(status, C.COMPONENT_SEFAZ_TLS)

    if gateway is False:
        return C.DIAG_LOCAL_NETWORK
    if gateway is True and server is False:
        return C.DIAG_SERVER_COMM
    if server is True and internet is False:
        return C.DIAG_INTERNET
    if internet is True and dns is False:
        return C.DIAG_DNS
    if dns is True and tcp is False:
        return C.DIAG_SEFAZ_PATH
    if tcp is True and tls is False:
        return C.DIAG_TLS
    known = [gateway, server, internet, dns, tcp, tls]
    if all(value is True for value in known):
        return C.DIAG_OK
    return C.DIAG_UNKNOWN


def active_wan_from_statuses(wan_statuses: Sequence[Mapping[str, Any]]) -> str | None:
    matches = [
        item for item in wan_statuses
        if item.get("active_route") is True
    ]
    return str(matches[0].get("wan_name")) if len(matches) == 1 else "WAN desconhecida"


def wan_line(wan_statuses: Sequence[Mapping[str, Any]]) -> str:
    """Resumo textual das WANs, usado nas mensagens do Telegram."""
    if not wan_statuses:
        return "WAN: sem dados da MikroTik"
    parts = []
    for item in wan_statuses:
        icon = {"up": "OK", "down": "DOWN"}.get(str(item.get("status")), "?")
        marker = " <- ativa" if item.get("active_route") else ""
        parts.append(f"{item.get('wan_name')} {item.get('provider')}: {icon}{marker}")
    return " / ".join(parts)


def _down_wans(wan_statuses: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [item for item in wan_statuses if str(item.get("status")) == "down"]


def fleet_diagnosis(
    component: str,
    affected: Sequence[str],
    statuses: Mapping[str, Mapping[str, Any]],
    wan_statuses: Sequence[Mapping[str, Any]],
    total_machines: int,
) -> str:
    """Diagnostico correlacionado entre caixas - plano 13 e 30."""
    affected = list(affected)
    total = max(total_machines, len(statuses), 1)
    is_general = len(affected) >= 2 or len(affected) == total

    wan_txt = wan_line(wan_statuses)
    down = _down_wans(wan_statuses)
    down_txt = ", ".join(f"{w.get('wan_name')} ({w.get('provider')})" for w in down)

    if len(affected) == 1 and not is_general:
        machine = affected[0]
        base = machine_diagnosis(statuses.get(machine, {}))
        return (
            f"Os testes indicam uma ocorrência concentrada no {machine}.\n"
            f"Leitura do monitor: {base}.\n{wan_txt}"
        )

    if component == C.COMPONENT_GATEWAY:
        return (
            f"Os testes apontam instabilidade na rede local dos seguintes caixas: {', '.join(affected)}.\n"
            f"Verificar a conexão local e os equipamentos de rede.\n{wan_txt}"
        )

    if component == C.COMPONENT_SERVER:
        return (
            f"Os testes não conseguiram acessar o servidor da loja a partir de "
            f"{', '.join(affected)}.\n{wan_txt}"
        )

    if component == C.COMPONENT_INTERNET:
        if down:
            return f"Os testes indicam falta de conectividade externa, coincidente com link indisponível: {down_txt}.\n{wan_txt}"
        return (
            f"Os testes de internet falharam nos caixas {', '.join(affected)}. "
            f"A origem ainda precisa ser confirmada.\n{wan_txt}"
        )

    if component == C.COMPONENT_DNS:
        return (
            f"A consulta de endereço da SEFAZ falhou nos caixas {', '.join(affected)}.\n"
            f"Os testes de internet responderam; a resolução do nome ainda precisa ser verificada.\n{wan_txt}"
        )

    if component in (C.COMPONENT_SEFAZ_TCP, C.COMPONENT_SEFAZ_TLS):
        extra = ""
        if down:
            extra = f"\nUma WAN esta fora: {down_txt}."
        return (
            f"Os testes de conexão até a SEFAZ falharam nos caixas {', '.join(affected)}.\n"
            f"Rede local, servidor e internet responderam normalmente; a origem final não foi confirmada.{extra}\n{wan_txt}"
        )

    if component == C.COMPONENT_TEF:
        return f"TEF fora do escopo ativo do monitor.\n{wan_txt}"

    return f"Incidente de {component} afetando {', '.join(affected)}.\n{wan_txt}"


def incident_severity(component: str, affected: Sequence[str]) -> str:
    if component == C.COMPONENT_GATEWAY:
        return "critical"
    if component in (C.COMPONENT_SEFAZ_TCP, C.COMPONENT_SEFAZ_TLS, C.COMPONENT_INTERNET):
        return "critical" if len(affected) >= 2 else "warning"
    return "warning"
