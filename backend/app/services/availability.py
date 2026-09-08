from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

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
from app.schemas.availability import AvailabilitySlot, AvailabilitySlotsResponse

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


def _utc_datetime(target_date: date, target_time: time) -> datetime:
    return datetime.combine(target_date, target_time, tzinfo=UTC)


def _overlap_interval(
    start: datetime, end: datetime, target_date: date
) -> Interval | None:
    day_start = _utc_datetime(target_date, time.min)
    day_end = day_start + timedelta(days=1)
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
            _utc_datetime(target_date, window.start_time),
            _utc_datetime(target_date, window.end_time),
        )
        for window in windows
    ]
    blocked: list[Interval] = []
    for item in breaks:
        if item.day_of_week == target_date.weekday():
            blocked.append(
                (
                    _utc_datetime(target_date, item.start_time),
                    _utc_datetime(target_date, item.end_time),
                )
            )

    for blackout in blackouts:
        overlap = _overlap_interval(
            blackout.blackout_start, blackout.blackout_end, target_date
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
    service_id: UUID,
    target_date: date,
    provider_id: UUID | None = None,
    slot_interval_minutes: int = 15,
) -> AvailabilitySlotsResponse | None:
    service = db.scalar(
        select(Service).where(
            Service.id == service_id,
            Service.status == ServiceStatus.ACTIVE,
        )
    )
    if service is None:
        return None

    provider_query = (
        select(Provider)
        .join(ProviderService, ProviderService.provider_id == Provider.id)
        .where(
            ProviderService.service_id == service_id,
            ProviderService.is_active.is_(True),
            Provider.availability_status == AvailabilityStatus.AVAILABLE,
        )
    )
    if provider_id is not None:
        provider_query = provider_query.where(Provider.id == provider_id)
    providers = list(db.scalars(provider_query).unique().all())

    slots: list[AvailabilitySlot] = []
    day_start = _utc_datetime(target_date, time.min)
    day_end = day_start + timedelta(days=1)
    for provider in providers:
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
        blackouts = list(
            db.scalars(
                select(ProviderBlackoutDate).where(
                    ProviderBlackoutDate.provider_id == provider.id,
                    ProviderBlackoutDate.blackout_start < day_end,
                    ProviderBlackoutDate.blackout_end > day_start,
                )
            ).all()
        )
        breaks = list(
            db.scalars(
                select(ProviderBreak).where(
                    ProviderBreak.provider_id == provider.id,
                    ProviderBreak.day_of_week == target_date.weekday(),
                )
            ).all()
        )
        slots.extend(
            _provider_slots(
                provider,
                service,
                target_date,
                appointments,
                blackouts,
                breaks,
                timedelta(minutes=slot_interval_minutes),
            )
        )

    slots.sort(key=lambda slot: (slot.start, slot.provider_name))
    return AvailabilitySlotsResponse(
        service_id=service_id,
        date=target_date,
        slot_interval_minutes=slot_interval_minutes,
        slots=slots,
    )
