import calendar
from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from app.core.timezones import TimezoneValidationError, get_timezone, to_utc

MAX_OCCURRENCES = 52


class RecurrenceValidationError(ValueError):
    """Raised when a recurrence rule cannot produce valid occurrences."""


def _normalize_choice(value: str | Enum, field_name: str) -> str:
    choice = value.name if isinstance(value, Enum) else value
    if not isinstance(choice, str):
        raise RecurrenceValidationError(f"{field_name} is invalid")
    return choice.upper()


def _validate_date(value: date, field_name: str) -> None:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise RecurrenceValidationError(f"{field_name} must be a date")


def _occurrence_date(
    start_date: date,
    frequency: str,
    interval: int,
    occurrence_index: int,
) -> date:
    if frequency == "WEEKLY":
        try:
            return start_date + timedelta(weeks=interval * occurrence_index)
        except OverflowError as error:
            raise RecurrenceValidationError(
                "Generated occurrence date is out of range"
            ) from error

    month_index = (
        start_date.year * 12 + start_date.month - 1 + interval * occurrence_index
    )
    year, month_index = divmod(month_index, 12)
    if year < 1 or year > 9999:
        raise RecurrenceValidationError("Generated occurrence date is out of range")
    month = month_index + 1
    day = min(start_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _resolve_local_datetime(
    local_datetime: datetime, timezone_name: str, timezone: ZoneInfo
) -> datetime:
    resolved: dict[int, tuple[datetime, datetime]] = {}
    for fold in (0, 1):
        local_candidate = local_datetime.replace(tzinfo=timezone, fold=fold)
        utc_candidate = to_utc(local_candidate, timezone_name)
        round_trip = utc_candidate.astimezone(timezone)
        if round_trip.replace(tzinfo=None) == local_datetime:
            resolved[fold] = local_candidate, utc_candidate

    if not resolved:
        raise RecurrenceValidationError(
            f"Local occurrence time {local_datetime.isoformat()} does not exist "
            f"in timezone {timezone_name}"
        )

    # fold=0 is also valid for normal local times and selects the earlier
    # occurrence when both folds are valid during a backward DST transition.
    _, utc_datetime = resolved[min(resolved)]
    if utc_datetime.astimezone(timezone).replace(tzinfo=None) != local_datetime:
        raise RecurrenceValidationError(
            f"Local occurrence time {local_datetime.isoformat()} could not be "
            f"resolved in timezone {timezone_name}"
        )
    return utc_datetime.astimezone(UTC)


def generate_occurrence_starts(
    *,
    start_date: date,
    local_start_time: time,
    timezone_name: str,
    frequency: str | Enum,
    interval: int,
    end_mode: str | Enum,
    occurrence_count: int | None = None,
    end_date: date | None = None,
    max_occurrences: int = MAX_OCCURRENCES,
) -> list[datetime]:
    """Generate UTC-aware starts from a provider-local recurrence rule."""
    _validate_date(start_date, "start_date")
    if not isinstance(local_start_time, time) or local_start_time.tzinfo is not None:
        raise RecurrenceValidationError("local_start_time must be a naive time")
    if not isinstance(timezone_name, str) or not timezone_name:
        raise RecurrenceValidationError("timezone_name must be a valid IANA timezone")
    if isinstance(interval, bool) or not isinstance(interval, int):
        raise RecurrenceValidationError("interval must be an integer")
    if (
        isinstance(max_occurrences, bool)
        or not isinstance(max_occurrences, int)
        or not 1 <= max_occurrences <= MAX_OCCURRENCES
    ):
        raise RecurrenceValidationError(
            f"max_occurrences must be between 1 and {MAX_OCCURRENCES}"
        )

    frequency_value = _normalize_choice(frequency, "frequency")
    if frequency_value == "WEEKLY":
        if interval not in (1, 2):
            raise RecurrenceValidationError("WEEKLY interval must be 1 or 2")
    elif frequency_value == "MONTHLY":
        if interval != 1:
            raise RecurrenceValidationError("MONTHLY interval must be 1")
    else:
        raise RecurrenceValidationError("frequency must be WEEKLY or MONTHLY")

    end_mode_value = _normalize_choice(end_mode, "end_mode")
    if end_mode_value == "COUNT":
        if occurrence_count is None:
            raise RecurrenceValidationError("COUNT end mode requires occurrence_count")
        if end_date is not None:
            raise RecurrenceValidationError("COUNT end mode cannot include end_date")
        if (
            isinstance(occurrence_count, bool)
            or not isinstance(occurrence_count, int)
            or not 1 <= occurrence_count <= max_occurrences
        ):
            raise RecurrenceValidationError(
                f"occurrence_count must be between 1 and {max_occurrences}"
            )
    elif end_mode_value == "END_DATE":
        if end_date is None:
            raise RecurrenceValidationError("END_DATE end mode requires end_date")
        if occurrence_count is not None:
            raise RecurrenceValidationError(
                "END_DATE end mode cannot include occurrence_count"
            )
        _validate_date(end_date, "end_date")
        if end_date < start_date:
            raise RecurrenceValidationError("end_date cannot be before start_date")
    else:
        raise RecurrenceValidationError("end_mode must be COUNT or END_DATE")

    try:
        timezone = get_timezone(timezone_name)
    except TimezoneValidationError as error:
        raise RecurrenceValidationError(str(error)) from error

    starts: list[datetime] = []
    occurrence_index = 0
    while True:
        if end_mode_value == "COUNT" and occurrence_index >= occurrence_count:
            return starts

        occurrence_date = _occurrence_date(
            start_date, frequency_value, interval, occurrence_index
        )
        if end_mode_value == "END_DATE" and occurrence_date > end_date:
            return starts
        if len(starts) >= max_occurrences:
            raise RecurrenceValidationError(
                f"Recurrence cannot exceed {max_occurrences} occurrences"
            )

        local_datetime = datetime.combine(occurrence_date, local_start_time)
        starts.append(_resolve_local_datetime(local_datetime, timezone_name, timezone))
        occurrence_index += 1
