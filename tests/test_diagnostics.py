"""Testes da arvore de diagnostico - plano secoes 13, 14 e 30."""

from __future__ import annotations

from server.services import diagnostics as diag
from shared import constants as C
from tests.conftest import status


def test_gateway_fail_diagnostica_rede_local():
    assert diag.machine_diagnosis(status("CAIXA02", gateway_ok=False)) == C.DIAG_LOCAL_NETWORK


def test_gateway_ok_servidor_fail():
    result = diag.machine_diagnosis(status("CAIXA02", server_ok=False))
    assert result == C.DIAG_SERVER_COMM


def test_internet_fail_com_servidor_ok():
    assert diag.machine_diagnosis(status("CAIXA02", internet_ok=False)) == C.DIAG_INTERNET


def test_dns_fail_com_internet_ok():
    assert diag.machine_diagnosis(status("CAIXA02", dns_ok=False)) == C.DIAG_DNS


def test_sefaz_tcp_fail_com_dns_ok():
    assert diag.machine_diagnosis(status("CAIXA02", sefaz_tcp_ok=False)) == C.DIAG_SEFAZ_PATH


def test_tls_fail_com_tcp_ok():
    assert diag.machine_diagnosis(status("CAIXA02", sefaz_tls_ok=False)) == C.DIAG_TLS


def test_tef_fica_fora_do_diagnostico_ativo():
    candidate = status("CAIXA02", tef_connected=False)
    assert diag.component_status(candidate, C.COMPONENT_TEF) is None
    assert diag.machine_diagnosis(candidate) == C.DIAG_OK


def test_tudo_ok_e_operacional():
    assert diag.machine_diagnosis(status("CAIXA02")) == C.DIAG_OK


def test_valores_desconhecidos_nao_geram_falso_diagnostico():
    resultado = diag.machine_diagnosis(
        {
            "gateway_ok": None,
            "server_ok": None,
            "internet_ok": None,
            "dns_ok": None,
            "sefaz_tcp_ok": None,
            "sefaz_tls_ok": None,
            "tef_connected": None,
        }
    )
    assert resultado == C.DIAG_UNKNOWN


def test_ordem_de_causa_raiz_prevalece():
    """Gateway fora domina qualquer outra falha."""
    resultado = diag.machine_diagnosis(
        status("CAIXA02", gateway_ok=False, sefaz_tcp_ok=False, sefaz_tls_ok=False)
    )
    assert resultado == C.DIAG_LOCAL_NETWORK


def test_frota_geral_aponta_caminho_da_operadora():
    statuses = {name: status(name, sefaz_tcp_ok=False) for name in ("CAIXA01", "CAIXA02", "CAIXA03")}
    texto = diag.fleet_diagnosis(C.COMPONENT_SEFAZ_TCP, list(statuses), statuses, [], 3)
    assert "conexão até a SEFAZ" in texto
    assert "origem final não foi confirmada" in texto
    assert "CAIXA01" in texto


def test_frota_localizada_aponta_o_caixa():
    statuses = {
        "CAIXA01": status("CAIXA01"),
        "CAIXA02": status("CAIXA02", sefaz_tcp_ok=False),
        "CAIXA03": status("CAIXA03"),
    }
    texto = diag.fleet_diagnosis(C.COMPONENT_SEFAZ_TCP, ["CAIXA02"], statuses, [], 3)
    assert "CAIXA02" in texto
    assert "concentrada" in texto.lower()


def test_frota_associa_falha_a_wan_fora():
    statuses = {name: status(name, internet_ok=False) for name in ("CAIXA01", "CAIXA02")}
    wans = [{"wan_name": "WAN1", "provider": "STARLINK", "status": "down", "active_route": False}]
    texto = diag.fleet_diagnosis(C.COMPONENT_INTERNET, list(statuses), statuses, wans, 2)
    assert "STARLINK" in texto


def test_wan_ativa_e_escolhida_pela_rota_default():
    wans = [
        {"wan_name": "WAN1", "status": "up", "active_route": False},
        {"wan_name": "WAN2", "status": "up", "active_route": True},
    ]
    assert diag.active_wan_from_statuses(wans) == "WAN2"


def test_wan_ambigua_nao_e_escolhida_por_ordem():
    wans = [
        {"wan_name": "WAN1", "status": "up", "active_route": None},
        {"wan_name": "WAN2", "status": "up", "active_route": None},
    ]
    assert diag.active_wan_from_statuses(wans) == "WAN desconhecida"
