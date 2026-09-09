from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.appointment import Appointment, AppointmentStatus
from app.models.appointment_cancellation import AppointmentCancellation
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider
from app.models.service import Service, ServiceStatus
from app.schemas.appointment import (
    AppointmentCancellationCreate,
    AppointmentCreate,
    AppointmentUpdate,
)


class BookingValidationError(ValueError):
    pass


class BookingConflictError(BookingValidationError):
    pass


class CancellationValidationError(BookingValidationError):
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


def _validate_slot(
    db: Session,
    appointment_start: datetime,
    duration_minutes: int,
    provider: Provider,
    exclude_appointment_id=None,
) -> tuple[datetime, datetime]:
    try:
        zone = ZoneInfo(provider.timezone)
    except ZoneInfoNotFoundError as error:
        raise BookingValidationError("Provider has an invalid timezone") from error

    start_utc = _utc(appointment_start)
    if start_utc <= datetime.now(UTC):
        raise BookingValidationError("Appointments cannot be booked in the past")

    end_utc = start_utc + timedelta(minutes=duration_minutes)
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

    overlapping_query = select(Appointment.id).where(
        Appointment.provider_id == provider.id,
        Appointment.status != AppointmentStatus.CANCELLED,
        Appointment.appointment_start < end_utc,
        Appointment.appointment_end > start_utc,
    )
    if exclude_appointment_id is not None:
        overlapping_query = overlapping_query.where(
            Appointment.id != exclude_appointment_id
        )
    if db.scalar(overlapping_query) is not None:
        raise BookingConflictError("Appointment slot is already booked")

    return start_utc, end_utc


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

    start_utc, end_utc = _validate_slot(
        db, payload.appointment_start, service.duration_minutes, provider
    )

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


def update_appointment(
    db: Session, appointment: Appointment, payload: AppointmentUpdate
) -> Appointment:
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("status") == AppointmentStatus.CANCELLED:
        raise BookingValidationError(
            "Use the cancellation endpoint to cancel an appointment"
        )
    new_start = changes.pop("appointment_start", None)
    if new_start is not None:
        provider = db.scalar(
            select(Provider)
            .where(Provider.id == appointment.provider_id)
            .with_for_update()
        )
        if provider is None:
            raise BookingValidationError("Provider not found")
        start_utc, end_utc = _validate_slot(
            db,
            new_start,
            appointment.duration_minutes,
            provider,
            appointment.id,
        )
        appointment.appointment_start = start_utc
        appointment.appointment_end = end_utc

    for field, value in changes.items():
        setattr(appointment, field, value)

    db.commit()
    db.refresh(appointment)
    return appointment


def cancel_appointment(
    db: Session,
    appointment_id,
    payload: AppointmentCancellationCreate | None = None,
) -> AppointmentCancellation:
    payload = payload or AppointmentCancellationCreate()
    appointment_snapshot = db.scalar(
        select(Appointment).where(Appointment.id == appointment_id)
    )
    if appointment_snapshot is None:
        raise CancellationValidationError("Appointment not found")

    db.scalar(
        select(Provider)
        .where(Provider.id == appointment_snapshot.provider_id)
        .with_for_update()
    )
    appointment = db.scalar(
        select(Appointment).where(Appointment.id == appointment_id).with_for_update()
    )
    if appointment is None:
        raise CancellationValidationError("Appointment not found")
    if appointment.status == AppointmentStatus.CANCELLED:
        raise CancellationValidationError("Appointment is already cancelled")
    if appointment.status == AppointmentStatus.COMPLETED:
        raise CancellationValidationError("Completed appointments cannot be cancelled")

    cancellation_deadline = appointment.appointment_start - timedelta(
        minutes=settings.cancellation_grace_period_minutes
    )
    if datetime.now(UTC) >= cancellation_deadline:
        raise CancellationValidationError(
            "Appointments cannot be cancelled within the cancellation grace period"
        )

    appointment.status = AppointmentStatus.CANCELLED
    cancellation = AppointmentCancellation(
        appointment_id=appointment.id,
        **payload.model_dump(),
    )
    db.add(cancellation)
    db.commit()
    db.refresh(cancellation)
    return cancellation
