from datetime import datetime, timedelta, timezone

from app.services.availability import generate_slot_starts, subtract_intervals


def test_generate_slot_starts_within_working_hours():
    free_intervals = [
        (
            datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc),
        )
    ]

    starts = generate_slot_starts(
        free_intervals=free_intervals,
        duration=timedelta(minutes=30),
        buffer=timedelta(0),
        interval=timedelta(minutes=15),
    )

    assert starts == [
        datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 14, 9, 15, tzinfo=timezone.utc),
        datetime(2026, 9, 14, 9, 30, tzinfo=timezone.utc),
    ]


def test_break_is_removed_from_available_interval():
    working_intervals = [
        (
            datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 14, 17, 0, tzinfo=timezone.utc),
        )
    ]

    break_intervals = [
        (
            datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 14, 13, 0, tzinfo=timezone.utc),
        )
    ]

    free_intervals = subtract_intervals(
        working_intervals,
        break_intervals,
    )

    assert free_intervals == [
        (
            datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
        ),
        (
            datetime(2026, 9, 14, 13, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 14, 17, 0, tzinfo=timezone.utc),
        ),
    ]


def test_buffer_time_reduces_available_slot_starts():
    free_intervals = [
        (
            datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc),
        )
    ]

    starts = generate_slot_starts(
        free_intervals=free_intervals,
        duration=timedelta(minutes=30),
        buffer=timedelta(minutes=15),
        interval=timedelta(minutes=15),
    )

    assert starts == [
        datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 14, 9, 15, tzinfo=timezone.utc),
    ]


def test_blackout_interval_is_removed_from_available_interval():
    working_intervals = [
        (
            datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 14, 17, 0, tzinfo=timezone.utc),
        )
    ]

    blackout_intervals = [
        (
            datetime(2026, 9, 14, 14, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc),
        )
    ]

    free_intervals = subtract_intervals(
        working_intervals,
        blackout_intervals,
    )

    assert free_intervals == [
        (
            datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 14, 14, 0, tzinfo=timezone.utc),
        ),
        (
            datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 14, 17, 0, tzinfo=timezone.utc),
        ),
    ]
