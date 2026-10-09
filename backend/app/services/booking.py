import logging
from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment, AppointmentStatus
from app.models.appointment_cancellation import AppointmentCancellation
from app.models.customer import Customer
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider
from app.models.service import Service, ServiceStatus
from app.models.user import UserRole
from app.schemas.appointment import (
    AppointmentCancellationCreate,
    AppointmentCreate,
    AppointmentRescheduleCreate,
    AppointmentUpdate,
)
from app.services.appointment_intervals import appointment_blocked_interval
from app.tasks.notification_tasks import (
    enqueue_confirmation_notification,
    schedule_appointment_notifications,
    send_cancellation_notification,
    send_confirmation_status_notification,
    send_reschedule_notification,
)

logger = logging.getLogger(__name__)


class BookingValidationError(ValueError):
    pass


class BookingConflictError(BookingValidationError):
    pass


class CancellationValidationError(BookingValidationError):
    pass


MODIFICATION_CUTOFF_HOURS = 2


def get_booking_status(
    appointment_start: datetime, duration_minutes: int, status: str | AppointmentStatus, now_utc: datetime
) -> str:
    if status in (AppointmentStatus.CANCELLED, "CANCELLED", "cancelled"):
        return "cancelled"

    appointment_end = appointment_start + timedelta(minutes=duration_minutes)
    if now_utc >= appointment_end:
        return "completed"
    if appointment_start <= now_utc < appointment_end:
        return "in_progress"
    return "confirmed"


def can_modify_booking(appointment_start: datetime, now_utc: datetime) -> bool:
    cutoff_time = appointment_start - timedelta(hours=MODIFICATION_CUTOFF_HOURS)
    return now_utc < cutoff_time


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
    buffer_time_minutes: int = 0,
) -> tuple[datetime, datetime]:
    try:
        zone = ZoneInfo(provider.timezone)
    except ZoneInfoNotFoundError as error:
        raise BookingValidationError("Provider has an invalid timezone") from error

    start_utc = _utc(appointment_start)
    if start_utc <= datetime.now(UTC):
        raise BookingValidationError("Appointments cannot be booked in the past")

    end_utc = start_utc + timedelta(minutes=duration_minutes)
    blocked_end_utc = end_utc + timedelta(minutes=buffer_time_minutes)
    local_start = start_utc.astimezone(zone)
    local_blocked_end = blocked_end_utc.astimezone(zone)
    if local_start.date() != local_blocked_end.date():
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
    if start_utc < working_start or blocked_end_utc > working_end:
        raise BookingValidationError("Appointment is outside working hours")

    for break_window in provider.breaks:
        if break_window.day_of_week != local_start.weekday():
            continue
        break_start, break_end = _local_interval(
            local_start.date(), break_window.start_time, break_window.end_time, zone
        )
        if start_utc < break_end and blocked_end_utc > break_start:
            raise BookingValidationError("Appointment overlaps a provider break")

    for blackout in provider.blackout_dates:
        blackout_start = _utc(blackout.blackout_start)
        blackout_end = _utc(blackout.blackout_end)
        if start_utc < blackout_end and blocked_end_utc > blackout_start:
            raise BookingValidationError("Appointment overlaps a provider blackout")

    existing_start, existing_blocked_end = appointment_blocked_interval()
    overlapping_query = select(Appointment.id).where(
        Appointment.provider_id == provider.id,
        Appointment.status != AppointmentStatus.CANCELLED,
        existing_start < blocked_end_utc,
        existing_blocked_end > start_utc,
    )
    if exclude_appointment_id is not None:
        overlapping_query = overlapping_query.where(
            Appointment.id != exclude_appointment_id
        )
    if db.scalar(overlapping_query) is not None:
        raise BookingConflictError("Appointment slot is already booked")

    return start_utc, end_utc


def _lock_provider_and_get_service(
    db: Session, provider_id: UUID, service_id: UUID
) -> tuple[Provider, Service]:
    provider = db.scalar(
        select(Provider).where(Provider.id == provider_id).with_for_update()
    )
    if provider is None:
        raise BookingValidationError("Provider not found")
    if provider.availability_status != AvailabilityStatus.AVAILABLE:
        raise BookingValidationError("Provider is not available")

    service = db.scalar(
        select(Service)
        .join(ProviderService, ProviderService.service_id == Service.id)
        .where(
            Service.id == service_id,
            Service.status == ServiceStatus.ACTIVE,
            ProviderService.provider_id == provider.id,
            ProviderService.is_active.is_(True),
        )
    )
    if service is None:
        raise BookingValidationError("Active service is not offered by provider")
    return provider, service


def _build_appointment(
    payload: AppointmentCreate,
    customer: Customer | None,
    service: Service,
    start_utc: datetime,
    end_utc: datetime,
    *,
    series_id: UUID | None = None,
    occurrence_number: int | None = None,
) -> Appointment:
    return Appointment(
        **payload.model_dump(exclude={"appointment_start"}),
        customer_id=customer.id if customer is not None else None,
        appointment_start=start_utc,
        appointment_end=end_utc,
        duration_minutes=service.duration_minutes,
        buffer_time_minutes=service.buffer_time_minutes or 0,
        series_id=series_id,
        occurrence_number=occurrence_number,
    )


def create_appointment(
    db: Session, payload: AppointmentCreate, customer: Customer | None = None
) -> Appointment:
    provider, service = _lock_provider_and_get_service(
        db, payload.provider_id, payload.service_id
    )

    start_utc, end_utc = _validate_slot(
        db,
        payload.appointment_start,
        service.duration_minutes,
        provider,
        buffer_time_minutes=service.buffer_time_minutes or 0,
    )

    appointment = _build_appointment(
        payload,
        customer,
        service,
        start_utc,
        end_utc,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    try:
        enqueue_confirmation_notification(appointment)
    except Exception:
        logger.exception(
            "Unable to enqueue confirmation notification for appointment %s",
            appointment.id,
        )
    try:
        schedule_appointment_notifications(appointment)
    except Exception:
        logger.exception(
            "Unable to schedule notifications for appointment %s", appointment.id
        )
    return appointment


def update_appointment(
    db: Session,
    appointment: Appointment,
    payload: AppointmentUpdate,
    user_role: UserRole | None = None,
) -> Appointment:
    changes = payload.model_dump(exclude_unset=True)
    rescheduled = "appointment_start" in changes
    confirmed = changes.get("status") == AppointmentStatus.CONFIRMED
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
            appointment.buffer_time_minutes,
        )
        appointment.appointment_start = start_utc
        appointment.appointment_end = end_utc

    for field, value in changes.items():
        setattr(appointment, field, value)

    db.commit()
    db.refresh(appointment)
    if confirmed:
        send_confirmation_status_notification.delay(str(appointment.id))
    if rescheduled:
        db.refresh(appointment)
        send_reschedule_notification.delay(str(appointment.id))
    return appointment


def cancel_appointment(
    db: Session,
    appointment_id,
    payload: AppointmentCancellationCreate | None = None,
    user_role: UserRole | None = None,
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

    now_utc = datetime.now(UTC)
    current_status = get_booking_status(
        appointment.appointment_start,
        appointment.duration_minutes,
        appointment.status,
        now_utc,
    )

    if current_status in ("in_progress", "completed", "cancelled"):
        raise CancellationValidationError(
            f"Cannot cancel appointment with status {current_status}"
        )

    from app.models.user import UserRole

    if user_role == UserRole.CUSTOMER or user_role is None:
        if not can_modify_booking(appointment.appointment_start, now_utc):
            raise CancellationValidationError(
                f"Bookings cannot be cancelled or rescheduled within {MODIFICATION_CUTOFF_HOURS} hours of the start time."
            )

    appointment.status = AppointmentStatus.CANCELLED
    cancellation = AppointmentCancellation(
        appointment_id=appointment.id,
        **payload.model_dump(),
    )
    db.add(cancellation)
    db.commit()
    db.refresh(cancellation)
    db.refresh(appointment)
    send_cancellation_notification.delay(str(appointment.id))
    return cancellation


def reschedule_appointment(
    db: Session,
    appointment_id,
    payload: AppointmentRescheduleCreate,
    user_role: UserRole | None = None,
) -> Appointment:
    appointment = db.scalar(
        select(Appointment).where(Appointment.id == appointment_id).with_for_update()
    )
    if appointment is None:
        raise BookingValidationError("Appointment not found")
    if appointment.status == AppointmentStatus.CANCELLED:
        raise BookingValidationError("Appointment is already cancelled")

    now_utc = datetime.now(UTC)
    current_status = get_booking_status(
        appointment.appointment_start,
        appointment.duration_minutes,
        appointment.status,
        now_utc,
    )

    if current_status in ("in_progress", "completed", "cancelled"):
        raise BookingValidationError(
            f"Cannot reschedule appointment with status {current_status}"
        )

    from app.models.user import UserRole

    if user_role == UserRole.CUSTOMER or user_role is None:
        if not can_modify_booking(appointment.appointment_start, now_utc):
            raise BookingValidationError(
                f"Bookings cannot be cancelled or rescheduled within {MODIFICATION_CUTOFF_HOURS} hours of the start time."
            )
        if not can_modify_booking(payload.appointment_start, now_utc):
            raise BookingValidationError(
                f"New booking slot must be at least {MODIFICATION_CUTOFF_HOURS} hours from now."
            )

    provider = db.scalar(
        select(Provider).where(Provider.id == appointment.provider_id).with_for_update()
    )
    if provider is None:
        raise BookingValidationError("Provider not found")
    if provider.availability_status != AvailabilityStatus.AVAILABLE:
        raise BookingValidationError("Provider is not available")

    start_utc, end_utc = _validate_slot(
        db,
        payload.appointment_start,
        appointment.duration_minutes,
        provider,
        exclude_appointment_id=appointment.id,
        buffer_time_minutes=appointment.buffer_time_minutes,
    )
    appointment.appointment_start = start_utc
    appointment.appointment_end = end_utc
    db.commit()
    db.refresh(appointment)
    send_reschedule_notification.delay(str(appointment.id))
    return appointment
