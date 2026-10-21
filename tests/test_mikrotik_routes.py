from __future__ import annotations

from server.services.mikrotik import MikrotikService, MikrotikSnapshot, WanReading


def make_snapshot() -> MikrotikSnapshot:
    return MikrotikSnapshot(
        wans=[
            WanReading("WAN1", "STARLINK", status="up"),
            WanReading("WAN2", "DESKTOP", status="up"),
            WanReading("WAN3", "OQUEI", status="up"),
        ]
    )


def test_rota_ativa_e_mapeada_pelo_gateway_exato(settings):
    settings.mikrotik_wan_gateways = {
        "STARLINK": "10.0.0.1",
        "DESKTOP": "10.0.1.1",
        "OQUEI": "10.0.2.1",
    }
    service = MikrotikService(settings)
    snapshot = make_snapshot()
    service._fill_active_route(
        snapshot,
        [{"dst-address": "0.0.0.0/0", "active": "true", "gateway": "10.0.1.1%ether2"}],
    )
    assert snapshot.active_wan == "WAN2"
    assert [wan.active_route for wan in snapshot.wans] == [False, True, False]


def test_sem_mapeamento_nao_escolhe_a_unica_wan_up(settings):
    settings.mikrotik_wan_gateways = {}
    service = MikrotikService(settings)
    snapshot = make_snapshot()
    service._fill_active_route(
        snapshot,
        [{"dst-address": "0.0.0.0/0", "active": True, "gateway": "10.0.0.1"}],
    )
    assert snapshot.active_wan is None
    assert all(wan.active_route is None for wan in snapshot.wans)


def test_ecmp_ou_gateway_duplicado_deixa_wan_desconhecida(settings):
    settings.mikrotik_wan_gateways = {"STARLINK": "10.0.0.1", "DESKTOP": "10.0.0.1"}
    service = MikrotikService(settings)
    snapshot = make_snapshot()
    service._fill_active_route(
        snapshot,
        [
            {"dst-address": "0.0.0.0/0", "active": True, "gateway": "10.0.0.1"},
            {"dst-address": "0.0.0.0/0", "active": True, "gateway": "10.0.1.1"},
        ],
    )
    assert snapshot.active_wan is None
    assert all(wan.active_route is None for wan in snapshot.wans)
