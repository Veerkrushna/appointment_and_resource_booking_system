from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class TimezoneValidationError(ValueError):
    pass


def get_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise TimezoneValidationError(f"Invalid timezone: {name}") from error


def to_local(value: datetime, timezone: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(get_timezone(timezone))