from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment, AppointmentStatus
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider
from app.models.service import Service, ServiceStatus
from app.schemas.appointment import AppointmentCreate


class BookingValidationError(ValueError):
    pass


class BookingConflictError(BookingValidationError):
    pass


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise BookingValidationError("appointment_start must include a timezone")
    return value.astimezone(UTC)


def _local_interval(date_value, start: time, end: time, zone: ZoneInfo):
    return (
        datetime.combine(date_value, start, tzinfo=zone).astimezone(UTC),
        datetime.combine(date_value, end, tzinfo=zone).astimezone(UTC),
    )


def create_appointment(db: Session, payload: AppointmentCreate) -> Appointment:
    provider = db.scalar(
        select(Provider).where(Provider.id == payload.provider_id).with_for_update()
    )
    if provider is None:
        raise BookingValidationError("Provider not found")
    if provider.availability_status != AvailabilityStatus.AVAILABLE:
        raise BookingValidationError("Provider is not available")

    service = db.scalar(
        select(Service)
        .join(ProviderService, ProviderService.service_id == Service.id)
        .where(
            Service.id == payload.service_id,
            Service.status == ServiceStatus.ACTIVE,
            ProviderService.provider_id == provider.id,
            ProviderService.is_active.is_(True),
        )
    )
    if service is None:
        raise BookingValidationError("Active service is not offered by provider")

    try:
        zone = ZoneInfo(provider.timezone)
    except ZoneInfoNotFoundError as error:
        raise BookingValidationError("Provider has an invalid timezone") from error

    start_utc = _utc(payload.appointment_start)
    now = datetime.now(UTC)
    if start_utc <= now:
        raise BookingValidationError("Appointments cannot be booked in the past")

    end_utc = start_utc + timedelta(minutes=service.duration_minutes)
    local_start = start_utc.astimezone(zone)
    local_end = end_utc.astimezone(zone)
    if local_start.date() != local_end.date():
        raise BookingValidationError("Appointment must fit within one working day")

    working_window = next(
        (
            item
            for item in provider.availability
            if item.day_of_week == local_start.weekday() and item.is_working_day
        ),
        None,
    )
    if (
        working_window is None
        or working_window.start_time is None
        or working_window.end_time is None
    ):
        raise BookingValidationError("Appointment is outside working hours")
    working_start, working_end = _local_interval(
        local_start.date(), working_window.start_time, working_window.end_time, zone
    )
    if start_utc < working_start or end_utc > working_end:
        raise BookingValidationError("Appointment is outside working hours")

    for break_window in provider.breaks:
        if break_window.day_of_week != local_start.weekday():
            continue
        break_start, break_end = _local_interval(
            local_start.date(), break_window.start_time, break_window.end_time, zone
        )
        if start_utc < break_end and end_utc > break_start:
            raise BookingValidationError("Appointment overlaps a provider break")

    for blackout in provider.blackout_dates:
        blackout_start = _utc(blackout.blackout_start)
        blackout_end = _utc(blackout.blackout_end)
        if start_utc < blackout_end and end_utc > blackout_start:
            raise BookingValidationError("Appointment overlaps a provider blackout")

    overlapping = db.scalar(
        select(Appointment.id).where(
            Appointment.provider_id == provider.id,
            Appointment.status != AppointmentStatus.CANCELLED,
            Appointment.appointment_start < end_utc,
            Appointment.appointment_end > start_utc,
        )
    )
    if overlapping is not None:
        raise BookingConflictError("Appointment slot is already booked")

    appointment = Appointment(
        **payload.model_dump(exclude={"appointment_start"}),
        appointment_start=start_utc,
        appointment_end=end_utc,
        duration_minutes=service.duration_minutes,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment
