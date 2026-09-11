from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment, AppointmentStatus
from app.models.availability import (
    ProviderBlackoutDate,
    ProviderBreak,
)
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider
from app.models.service import Service, ServiceStatus
from app.schemas.availability import AvailabilitySlot

Interval = tuple[datetime, datetime]


def subtract_intervals(
    available: Iterable[Interval], blocked: Iterable[Interval]
) -> list[Interval]:
    """Subtract overlapping blocked intervals from available intervals."""
    remaining = sorted(available)
    for blocked_start, blocked_end in sorted(blocked):
        next_remaining: list[Interval] = []
        for available_start, available_end in remaining:
            if blocked_end <= available_start or blocked_start >= available_end:
                next_remaining.append((available_start, available_end))
                continue
            if available_start < blocked_start:
                next_remaining.append((available_start, blocked_start))
            if blocked_end < available_end:
                next_remaining.append((blocked_end, available_end))
        remaining = next_remaining
    return remaining


def generate_slot_starts(
    free_intervals: Iterable[Interval],
    duration: timedelta,
    buffer: timedelta,
    interval: timedelta,
) -> list[datetime]:
    """Return starts whose appointment plus buffer fits within free time."""
    starts: list[datetime] = []
    for free_start, free_end in free_intervals:
        start = free_start
        while start + duration + buffer <= free_end:
            starts.append(start)
            start += interval
    return starts


def _provider_datetime(
    target_date: date, target_time: time, timezone: ZoneInfo
) -> datetime:
    return datetime.combine(target_date, target_time, tzinfo=timezone).astimezone(UTC)


def _overlap_interval(
    start: datetime, end: datetime, target_date: date, timezone: ZoneInfo
) -> Interval | None:
    day_start = _provider_datetime(target_date, time.min, timezone)
    day_end = _provider_datetime(target_date + timedelta(days=1), time.min, timezone)
    overlap_start = max(start, day_start)
    overlap_end = min(end, day_end)
    if overlap_start >= overlap_end:
        return None
    return overlap_start, overlap_end


def _provider_slots(
    provider: Provider,
    service: Service,
    target_date: date,
    appointments: list[Appointment],
    blackouts: list[ProviderBlackoutDate],
    breaks: list[ProviderBreak],
    slot_interval: timedelta,
    timezone: ZoneInfo,
) -> list[AvailabilitySlot]:
    windows = [
        availability
        for availability in provider.availability
        if availability.day_of_week == target_date.weekday()
        and availability.is_working_day
        and availability.start_time is not None
        and availability.end_time is not None
    ]
    if not windows:
        return []

    working_intervals = [
        (
            _provider_datetime(target_date, window.start_time, timezone),
            _provider_datetime(target_date, window.end_time, timezone),
        )
        for window in windows
    ]
    blocked: list[Interval] = []
    for item in breaks:
        if item.day_of_week == target_date.weekday():
            blocked.append(
                (
                    _provider_datetime(target_date, item.start_time, timezone),
                    _provider_datetime(target_date, item.end_time, timezone),
                )
            )

    for blackout in blackouts:
        overlap = _overlap_interval(
            blackout.blackout_start, blackout.blackout_end, target_date, timezone
        )
        if overlap is not None:
            blocked.append(overlap)

    service_buffer = timedelta(minutes=service.buffer_time_minutes or 0)
    for appointment in appointments:
        blocked.append(
            (
                appointment.appointment_start,
                appointment.appointment_end + service_buffer,
            )
        )

    free_intervals = subtract_intervals(working_intervals, blocked)
    starts = generate_slot_starts(
        free_intervals,
        timedelta(minutes=service.duration_minutes),
        service_buffer,
        slot_interval,
    )
    return [
        AvailabilitySlot(
            provider_id=provider.id,
            provider_name=provider.name,
            service_id=service.id,
            date=target_date,
            start=start,
            end=start + timedelta(minutes=service.duration_minutes),
            duration_minutes=service.duration_minutes,
        )
        for start in starts
    ]


def calculate_available_slots(
    db: Session,
    service_id: UUID | None,
    start_date: date,
    end_date: date,
    provider_id: UUID | None = None,
    slot_interval_minutes: int = 15,
) -> list[AvailabilitySlot] | None:
    if start_date > end_date:
        return None

    # ---------------------------------------------------------
    # 1. Find the services to calculate availability for
    # ---------------------------------------------------------
    service_query = select(Service).where(Service.status == ServiceStatus.ACTIVE)

    if service_id is not None:
        service_query = service_query.where(Service.id == service_id)

    services = list(db.scalars(service_query).all())

    if not services:
        return None

    # ---------------------------------------------------------
    # 2. Generate every date in the requested range
    # ---------------------------------------------------------
    dates: list[date] = []
    current_date = start_date

    while current_date <= end_date:
        dates.append(current_date)
        current_date += timedelta(days=1)

    # ---------------------------------------------------------
    # 3. Calculate slots for every service/provider/date
    # ---------------------------------------------------------
    slots: list[AvailabilitySlot] = []

    for service in services:
        provider_query = (
            select(Provider)
            .join(
                ProviderService,
                ProviderService.provider_id == Provider.id,
            )
            .where(
                ProviderService.service_id == service.id,
                ProviderService.is_active.is_(True),
                Provider.availability_status == AvailabilityStatus.AVAILABLE,
            )
        )

        if provider_id is not None:
            provider_query = provider_query.where(Provider.id == provider_id)

        providers = list(db.scalars(provider_query).unique().all())

        for provider in providers:
            try:
                timezone = ZoneInfo(provider.timezone)
            except ZoneInfoNotFoundError:
                continue

            for target_date in dates:
                # -------------------------------------------------
                # Determine the UTC boundaries for this provider's
                # local day.
                # -------------------------------------------------
                day_start = _provider_datetime(
                    target_date,
                    time.min,
                    timezone,
                )

                day_end = _provider_datetime(
                    target_date + timedelta(days=1),
                    time.min,
                    timezone,
                )

                # -------------------------------------------------
                # Existing appointments
                # -------------------------------------------------
                appointments = list(
                    db.scalars(
                        select(Appointment).where(
                            Appointment.provider_id == provider.id,
                            Appointment.status != AppointmentStatus.CANCELLED,
                            Appointment.appointment_start < day_end,
                            Appointment.appointment_end > day_start,
                        )
                    ).all()
                )

                # -------------------------------------------------
                # Blackout dates
                # -------------------------------------------------
                blackouts = list(
                    db.scalars(
                        select(ProviderBlackoutDate).where(
                            ProviderBlackoutDate.provider_id == provider.id,
                            ProviderBlackoutDate.blackout_start < day_end,
                            ProviderBlackoutDate.blackout_end > day_start,
                        )
                    ).all()
                )

                # -------------------------------------------------
                # Breaks
                # -------------------------------------------------
                breaks = list(
                    db.scalars(
                        select(ProviderBreak).where(
                            ProviderBreak.provider_id == provider.id,
                            ProviderBreak.day_of_week == target_date.weekday(),
                        )
                    ).all()
                )

                # -------------------------------------------------
                # Reuse the existing slot-generation algorithm
                # -------------------------------------------------
                slots.extend(
                    _provider_slots(
                        provider,
                        service,
                        target_date,
                        appointments,
                        blackouts,
                        breaks,
                        timedelta(minutes=slot_interval_minutes),
                        timezone,
                    )
                )

    # ---------------------------------------------------------
    # 4. Sort the complete result
    # ---------------------------------------------------------
    slots.sort(
        key=lambda slot: (
            slot.start,
            slot.provider_name,
            slot.service_id,
        )
    )

    return slots
