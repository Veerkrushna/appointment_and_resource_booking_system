from datetime import UTC, datetime

from app.core.timezones import to_local


def test_to_local_applies_daylight_saving_time():
    winter = to_local(datetime(2026, 1, 15, 15, tzinfo=UTC), "America/New_York")
    summer = to_local(datetime(2026, 7, 15, 15, tzinfo=UTC), "America/New_York")

    assert winter.isoformat() == "2026-01-15T10:00:00-05:00"
    assert summer.isoformat() == "2026-07-15T11:00:00-04:00"


def test_to_local_converts_utc_to_target_timezone():
    utc_time = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)

    local_time = to_local(utc_time, "Asia/Kolkata")

    assert local_time.isoformat() == "2026-09-15T17:30:00+05:30"
