from __future__ import annotations

from datetime import timedelta

from shared.schemas import WanStatus
from shared.timeutil import to_iso, utc_now


def test_daily_summary_queries_only_recent_incidents_and_wan_transitions(db):
    now = utc_now()
    since = to_iso(now - timedelta(hours=24))

    old_id = db.create_incident(
        "internet", "warning", to_iso(now - timedelta(hours=30)), ["CAIXA01"], "old", None
    )
    db.recover_incident(old_id, to_iso(now - timedelta(hours=29)))
    recent_id = db.create_incident(
        "sefaz_tls", "warning", to_iso(now - timedelta(hours=2)), ["CAIXA02"], "recent", None
    )
    db.recover_incident(recent_id, to_iso(now - timedelta(hours=1)))
    assert [item["type"] for item in db.incidents_since(since)] == ["sefaz_tls"]

    db.insert_wan_status(
        [
            WanStatus(timestamp=now - timedelta(hours=30), wan_name="WAN1", status="up", active_route=False),
            WanStatus(timestamp=now - timedelta(hours=2), wan_name="WAN1", status="down", active_route=False),
            WanStatus(timestamp=now - timedelta(hours=1), wan_name="WAN1", status="down", active_route=False),
            WanStatus(timestamp=now - timedelta(minutes=30), wan_name="WAN1", status="down", active_route=True),
        ]
    )
    transitions = db.wan_transitions(hours=24)
    assert len(transitions) == 2
    assert transitions[0]["previous_status"] == "up"
    assert transitions[0]["status"] == "down"
    assert transitions[1]["previous_active_route"] == 0
    assert transitions[1]["active_route"] == 1
