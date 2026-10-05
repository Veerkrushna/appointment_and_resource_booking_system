import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.models.appointment import Appointment, AppointmentStatus
from app.models.appointment_series import AppointmentSeries, AppointmentSeriesStatus
from app.models.customer import Customer
from app.schemas.appointment import AppointmentCreate
from app.schemas.appointment_series import AppointmentSeriesCreate
from app.services.booking import (
    BookingConflictError,
    BookingValidationError,
    _build_appointment,
    _lock_provider_and_get_service,
    _validate_slot,
    enqueue_confirmation_notification,
    schedule_appointment_notifications,
)
from app.services.recurrence import (
    RecurrenceValidationError,
    generate_occurrence_starts,
)
from app.tasks.notification_tasks import send_cancellation_notification

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OccurrenceConflict:
    occurrence_number: int
    date: str
    reason: str


class RecurringBookingConflictError(BookingConflictError):
    def __init__(self, conflicts: list[OccurrenceConflict]):
        self.conflicts = conflicts
        super().__init__("One or more recurring occurrences are unavailable")


class AppointmentSeriesPersistenceError(Exception):
    pass


class AppointmentSeriesNotFoundError(Exception):
    pass


class AppointmentSeriesCancellationConflictError(Exception):
    pass


def _occurrence_date(start_utc: datetime, timezone_name: str) -> str:
    return start_utc.astimezone(ZoneInfo(timezone_name)).date().isoformat()


def _appointment_payload(
    payload: AppointmentSeriesCreate, appointment_start: datetime
) -> AppointmentCreate:
    return AppointmentCreate(
        service_id=payload.service_id,
        provider_id=payload.provider_id,
        user_name=payload.user_name,
        user_email=payload.user_email,
        user_phone=payload.user_phone,
        appointment_start=appointment_start,
        notes=payload.notes,
    )


def _record_conflict(
    conflicts: dict[tuple[int, str], OccurrenceConflict],
    occurrence_number: int,
    occurrence_start: datetime,
    timezone_name: str,
    reason: str,
) -> None:
    key = occurrence_number, reason
    conflicts[key] = OccurrenceConflict(
        occurrence_number=occurrence_number,
        date=_occurrence_date(occurrence_start, timezone_name),
        reason=reason,
    )


def _enqueue_notifications(appointments: list[Appointment]) -> None:
    for appointment in appointments:
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
                "Unable to schedule notifications for appointment %s",
                appointment.id,
            )


def create_appointment_series(
    db: Session, payload: AppointmentSeriesCreate, customer: Customer
) -> tuple[AppointmentSeries, list[Appointment]]:
    appointments: list[Appointment] = []
    try:
        provider, service = _lock_provider_and_get_service(
            db, payload.provider_id, payload.service_id
        )
        starts = generate_occurrence_starts(
            start_date=payload.start_date,
            local_start_time=payload.local_start_time,
            timezone_name=provider.timezone,
            frequency=payload.frequency,
            interval=payload.interval,
            end_mode=payload.end_mode,
            occurrence_count=payload.occurrence_count,
            end_date=payload.end_date,
        )

        conflicts: dict[tuple[int, str], OccurrenceConflict] = {}
        validated_slots: list[tuple[datetime, datetime]] = []
        service_buffer = service.buffer_time_minutes or 0
        for occurrence_number, start in enumerate(starts, start=1):
            try:
                validated_slots.append(
                    _validate_slot(
                        db,
                        start,
                        service.duration_minutes,
                        provider,
                        buffer_time_minutes=service_buffer,
                    )
                )
            except BookingConflictError as error:
                validated_slots.append(
                    (
                        start,
                        start + timedelta(minutes=service.duration_minutes),
                    )
                )
                _record_conflict(
                    conflicts,
                    occurrence_number,
                    start,
                    provider.timezone,
                    str(error),
                )
            except BookingValidationError as error:
                validated_slots.append(
                    (
                        start,
                        start + timedelta(minutes=service.duration_minutes),
                    )
                )
                _record_conflict(
                    conflicts,
                    occurrence_number,
                    start,
                    provider.timezone,
                    str(error),
                )

        blocked_intervals = [
            (start, end + timedelta(minutes=service_buffer))
            for start, end in validated_slots
        ]
        for first_index, (first_start, first_end) in enumerate(blocked_intervals):
            for second_index in range(first_index + 1, len(blocked_intervals)):
                second_start, second_end = blocked_intervals[second_index]
                if first_start < second_end and second_start < first_end:
                    reason = "Overlaps another occurrence in this series"
                    _record_conflict(
                        conflicts,
                        first_index + 1,
                        starts[first_index],
                        provider.timezone,
                        reason,
                    )
                    _record_conflict(
                        conflicts,
                        second_index + 1,
                        starts[second_index],
                        provider.timezone,
                        reason,
                    )

        if conflicts:
            raise RecurringBookingConflictError(list(conflicts.values()))

        series = AppointmentSeries(
            customer_id=customer.id,
            provider_id=provider.id,
            service_id=service.id,
            frequency=payload.frequency,
            interval=payload.interval,
            start_date=payload.start_date,
            local_start_time=payload.local_start_time,
            timezone=provider.timezone,
            end_mode=payload.end_mode,
            occurrence_count=payload.occurrence_count,
            end_date=payload.end_date,
        )
        db.add(series)
        db.flush()

        appointments = [
            _build_appointment(
                _appointment_payload(payload, start),
                customer,
                service,
                start,
                end,
                series_id=series.id,
                occurrence_number=occurrence_number,
            )
            for occurrence_number, (start, end) in enumerate(validated_slots, start=1)
        ]
        db.add_all(appointments)
        db.flush()
        db.commit()
    except (
        RecurringBookingConflictError,
        BookingValidationError,
        RecurrenceValidationError,
    ):
        db.rollback()
        raise
    except SQLAlchemyError as error:
        db.rollback()
        raise AppointmentSeriesPersistenceError from error
    except Exception:
        db.rollback()
        raise

    _enqueue_notifications(appointments)
    return series, appointments


def cancel_appointment_series(
    db: Session, series_id: UUID, customer: Customer
) -> tuple[AppointmentSeries, list[UUID]]:
    try:
        series = db.scalar(
            select(AppointmentSeries)
            .where(AppointmentSeries.id == series_id)
            .with_for_update()
        )
        if series is None or series.customer_id != customer.id:
            raise AppointmentSeriesNotFoundError
        if series.status == AppointmentSeriesStatus.CANCELLED:
            raise AppointmentSeriesCancellationConflictError

        now_utc = datetime.now(UTC)
        appointments = db.scalars(
            select(Appointment)
            .where(
                Appointment.series_id == series.id,
                Appointment.appointment_start >= now_utc,
                Appointment.status == AppointmentStatus.CONFIRMED,
            )
            .order_by(Appointment.id)
            .with_for_update()
        ).all()
        cancelled_ids = [appointment.id for appointment in appointments]

        series.status = AppointmentSeriesStatus.CANCELLED
        for appointment in appointments:
            appointment.status = AppointmentStatus.CANCELLED

        db.commit()
    except (AppointmentSeriesNotFoundError, AppointmentSeriesCancellationConflictError):
        db.rollback()
        raise
    except SQLAlchemyError as error:
        db.rollback()
        raise AppointmentSeriesPersistenceError from error
    except Exception:
        db.rollback()
        raise

    for appointment_id in cancelled_ids:
        try:
            send_cancellation_notification.delay(str(appointment_id))
        except Exception:
            logger.exception(
                "Unable to enqueue cancellation notification for appointment %s",
                appointment_id,
            )

    return series, cancelled_ids


def get_appointment_series(
    db: Session, series_id: UUID, customer: Customer
) -> tuple[AppointmentSeries, list[Appointment]]:
    try:
        series = db.scalar(
            select(AppointmentSeries)
            .options(selectinload(AppointmentSeries.appointments))
            .where(
                AppointmentSeries.id == series_id,
                AppointmentSeries.customer_id == customer.id,
            )
        )
        if series is None:
            raise AppointmentSeriesNotFoundError
        appointments = sorted(
            series.appointments,
            key=lambda appointment: appointment.occurrence_number or 0,
        )
        return series, appointments
    except AppointmentSeriesNotFoundError:
        db.rollback()
        raise
    except SQLAlchemyError as error:
        db.rollback()
        raise AppointmentSeriesPersistenceError from error
