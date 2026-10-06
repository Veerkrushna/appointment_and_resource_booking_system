from datetime import UTC, date, datetime, time

import pytest

from app.models.appointment_series import (
    AppointmentSeriesEndMode,
    AppointmentSeriesFrequency,
)
from app.services.recurrence import (
    RecurrenceValidationError,
    generate_occurrence_starts,
)


def generate_counted(
    start_date: date,
    local_start_time: time = time(10),
    timezone_name: str = "UTC",
    frequency: str = "WEEKLY",
    interval: int = 1,
    occurrence_count: int = 3,
) -> list[datetime]:
    return generate_occurrence_starts(
        start_date=start_date,
        local_start_time=local_start_time,
        timezone_name=timezone_name,
        frequency=frequency,
        interval=interval,
        end_mode="COUNT",
        occurrence_count=occurrence_count,
    )


def test_weekly_recurrence_generates_counted_occurrences():
    starts = generate_counted(date(2026, 1, 5), occurrence_count=3)

    assert starts == [
        datetime(2026, 1, 5, 10, tzinfo=UTC),
        datetime(2026, 1, 12, 10, tzinfo=UTC),
        datetime(2026, 1, 19, 10, tzinfo=UTC),
    ]


def test_biweekly_recurrence_generates_every_two_weeks():
    starts = generate_counted(date(2026, 1, 5), interval=2, occurrence_count=3)

    assert [start.date() for start in starts] == [
        date(2026, 1, 5),
        date(2026, 1, 19),
        date(2026, 2, 2),
    ]


def test_end_date_is_inclusive_for_weekly_recurrence():
    starts = generate_occurrence_starts(
        start_date=date(2026, 1, 5),
        local_start_time=time(10),
        timezone_name="UTC",
        frequency="WEEKLY",
        interval=1,
        end_mode="END_DATE",
        end_date=date(2026, 1, 19),
    )

    assert [start.date() for start in starts] == [
        date(2026, 1, 5),
        date(2026, 1, 12),
        date(2026, 1, 19),
    ]


def test_existing_series_enum_members_are_accepted():
    starts = generate_occurrence_starts(
        start_date=date(2026, 1, 5),
        local_start_time=time(10),
        timezone_name="UTC",
        frequency=AppointmentSeriesFrequency.WEEKLY,
        interval=1,
        end_mode=AppointmentSeriesEndMode.COUNT,
        occurrence_count=1,
    )

    assert starts == [datetime(2026, 1, 5, 10, tzinfo=UTC)]


def test_monthly_recurrence_preserves_january_31_anchor():
    starts = generate_occurrence_starts(
        start_date=date(2026, 1, 31),
        local_start_time=time(10),
        timezone_name="UTC",
        frequency="MONTHLY",
        interval=1,
        end_mode="COUNT",
        occurrence_count=5,
    )

    assert [start.date() for start in starts] == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 5, 31),
    ]


def test_monthly_recurrence_preserves_january_30_anchor():
    starts = generate_occurrence_starts(
        start_date=date(2026, 1, 30),
        local_start_time=time(10),
        timezone_name="UTC",
        frequency="MONTHLY",
        interval=1,
        end_mode="COUNT",
        occurrence_count=4,
    )

    assert [start.date() for start in starts] == [
        date(2026, 1, 30),
        date(2026, 2, 28),
        date(2026, 3, 30),
        date(2026, 4, 30),
    ]


def test_monthly_recurrence_uses_leap_day_then_original_anchor():
    starts = generate_occurrence_starts(
        start_date=date(2024, 1, 29),
        local_start_time=time(10),
        timezone_name="UTC",
        frequency="MONTHLY",
        interval=1,
        end_mode="COUNT",
        occurrence_count=3,
    )

    assert [start.date() for start in starts] == [
        date(2024, 1, 29),
        date(2024, 2, 29),
        date(2024, 3, 29),
    ]


@pytest.mark.parametrize("occurrence_count", [0, 53])
def test_invalid_occurrence_count_is_rejected(occurrence_count):
    with pytest.raises(RecurrenceValidationError):
        generate_counted(date(2026, 1, 5), occurrence_count=occurrence_count)


def test_end_date_before_start_date_is_rejected():
    with pytest.raises(RecurrenceValidationError, match="before start_date"):
        generate_occurrence_starts(
            start_date=date(2026, 1, 5),
            local_start_time=time(10),
            timezone_name="UTC",
            frequency="WEEKLY",
            interval=1,
            end_mode="END_DATE",
            end_date=date(2026, 1, 4),
        )


def test_missing_count_value_is_rejected():
    with pytest.raises(RecurrenceValidationError, match="requires occurrence_count"):
        generate_occurrence_starts(
            start_date=date(2026, 1, 5),
            local_start_time=time(10),
            timezone_name="UTC",
            frequency="WEEKLY",
            interval=1,
            end_mode="COUNT",
        )


def test_missing_end_date_value_is_rejected():
    with pytest.raises(RecurrenceValidationError, match="requires end_date"):
        generate_occurrence_starts(
            start_date=date(2026, 1, 5),
            local_start_time=time(10),
            timezone_name="UTC",
            frequency="WEEKLY",
            interval=1,
            end_mode="END_DATE",
        )


@pytest.mark.parametrize(
    ("end_mode", "occurrence_count", "end_date"),
    [
        ("COUNT", 2, date(2026, 1, 19)),
        ("END_DATE", 2, date(2026, 1, 19)),
    ],
)
def test_conflicting_end_condition_values_are_rejected(
    end_mode, occurrence_count, end_date
):
    with pytest.raises(RecurrenceValidationError):
        generate_occurrence_starts(
            start_date=date(2026, 1, 5),
            local_start_time=time(10),
            timezone_name="UTC",
            frequency="WEEKLY",
            interval=1,
            end_mode=end_mode,
            occurrence_count=occurrence_count,
            end_date=end_date,
        )


@pytest.mark.parametrize(
    ("frequency", "interval"),
    [("DAILY", 1), ("WEEKLY", 0), ("WEEKLY", 3), ("MONTHLY", 2)],
)
def test_invalid_frequency_interval_combinations_are_rejected(frequency, interval):
    with pytest.raises(RecurrenceValidationError):
        generate_counted(date(2026, 1, 5), frequency=frequency, interval=interval)


def test_end_date_generation_obeys_maximum_occurrences():
    with pytest.raises(RecurrenceValidationError, match="cannot exceed 2"):
        generate_occurrence_starts(
            start_date=date(2026, 1, 5),
            local_start_time=time(10),
            timezone_name="UTC",
            frequency="WEEKLY",
            interval=1,
            end_mode="END_DATE",
            end_date=date(2026, 2, 2),
            max_occurrences=2,
        )


def test_utc_timezone_returns_utc_aware_starts():
    starts = generate_counted(
        date(2026, 1, 5),
        local_start_time=time(10),
        timezone_name="UTC",
        occurrence_count=1,
    )

    assert starts == [datetime(2026, 1, 5, 10, tzinfo=UTC)]
    assert all(
        start.tzinfo is UTC and start.utcoffset().total_seconds() == 0
        for start in starts
    )


def test_asia_kolkata_converts_local_time_to_utc():
    starts = generate_counted(
        date(2026, 1, 5),
        local_start_time=time(10),
        timezone_name="Asia/Kolkata",
        occurrence_count=1,
    )

    assert starts == [datetime(2026, 1, 5, 4, 30, tzinfo=UTC)]


def test_new_york_normal_time_preserves_local_wall_time_across_dst():
    starts = generate_counted(
        date(2026, 3, 1),
        local_start_time=time(10),
        timezone_name="America/New_York",
        frequency="WEEKLY",
        occurrence_count=2,
    )

    assert starts == [
        datetime(2026, 3, 1, 15, tzinfo=UTC),
        datetime(2026, 3, 8, 14, tzinfo=UTC),
    ]
    from zoneinfo import ZoneInfo

    assert [
        start.astimezone(ZoneInfo("America/New_York")).time() for start in starts
    ] == [
        time(10),
        time(10),
    ]
    assert all(start.tzinfo is UTC for start in starts)


def test_nonexistent_spring_forward_time_is_rejected():
    with pytest.raises(RecurrenceValidationError, match="does not exist"):
        generate_counted(
            date(2026, 3, 8),
            local_start_time=time(2, 30),
            timezone_name="America/New_York",
            occurrence_count=1,
        )


def test_ambiguous_fall_back_time_uses_fold_zero():
    starts = generate_counted(
        date(2026, 11, 1),
        local_start_time=time(1, 30),
        timezone_name="America/New_York",
        occurrence_count=1,
    )

    assert starts == [datetime(2026, 11, 1, 5, 30, tzinfo=UTC)]


def test_count_52_generates_exactly_52_occurrences():
    starts = generate_counted(date(2026, 1, 5), occurrence_count=52)

    assert len(starts) == 52
    assert starts[0] == datetime(2026, 1, 5, 10, tzinfo=UTC)
    assert starts[-1] == datetime(2026, 12, 28, 10, tzinfo=UTC)


def test_end_date_between_occurrences_excludes_later_occurrence():
    starts = generate_occurrence_starts(
        start_date=date(2026, 1, 5),
        local_start_time=time(10),
        timezone_name="UTC",
        frequency="WEEKLY",
        interval=1,
        end_mode="END_DATE",
        end_date=date(2026, 1, 18),
    )

    assert [start.date() for start in starts] == [
        date(2026, 1, 5),
        date(2026, 1, 12),
    ]


def test_monthly_january_31_preserves_anchor_through_leap_february():
    starts = generate_occurrence_starts(
        start_date=date(2024, 1, 31),
        local_start_time=time(10),
        timezone_name="UTC",
        frequency="MONTHLY",
        interval=1,
        end_mode="COUNT",
        occurrence_count=3,
    )

    assert [start.date() for start in starts] == [
        date(2024, 1, 31),
        date(2024, 2, 29),
        date(2024, 3, 31),
    ]
