from __future__ import annotations

from datetime import datetime, timezone

from shared.timeutil import format_local


def test_format_local_accepts_iso_timestamps_from_database():
    assert format_local("2026-10-13T12:00:00.000Z", "%H:%M") == "09:00"


def test_format_local_returns_placeholder_for_invalid_timestamp():
    assert format_local("not-a-timestamp") == "-"


def test_format_local_accepts_datetime_values():
    value = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
    assert format_local(value, "%H:%M") == "09:00"
