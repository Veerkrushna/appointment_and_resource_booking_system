from datetime import UTC, datetime

from app.core.timezones import to_local


def test_to_local_applies_daylight_saving_time():
    winter = to_local(datetime(2026, 1, 15, 15, tzinfo=UTC), "America/New_York")
    summer = to_local(datetime(2026, 7, 15, 15, tzinfo=UTC), "America/New_York")

    assert winter.isoformat() == "2026-01-15T10:00:00-05:00"
    assert summer.isoformat() == "2026-07-15T11:00:00-04:00"