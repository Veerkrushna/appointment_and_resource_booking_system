from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.api.routes.appointments import cancel_appointment_endpoint
from app.core.config import settings
from app.db.database import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.appointment_cancellation import AppointmentCancellation
from app.models.availability import ProviderAvailability
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.service import Service, ServiceStatus
from app.schemas.appointment import (
    AppointmentCancellationRequest,
    AppointmentCreate,
    AppointmentRescheduleCreate,
)
from app.services.booking import (
    BookingValidationError,
    _validate_slot,
    create_appointment,
    reschedule_appointment,
)


@pytest.fixture
def cancellation_records():
    db = SessionLocal()
    provider = Provider(
        name=f"Cancellation Provider {uuid4()}",
        type=ProviderType.PERSON,
        email=f"cancellation-{uuid4()}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    service = Service(
        name=f"Cancellation Service {uuid4()}",
        duration_minutes=30,
        category="Testing",
        capacity=1,
        buffer_time_minutes=0,
        status=ServiceStatus.ACTIVE,
    )
    db.add_all([provider, service])
    db.flush()
    db.add(
        ProviderService(
            provider_id=provider.id,
            service_id=service.id,
            is_active=True,
        )
    )
    db.add(
        ProviderAvailability(
            provider_id=provider.id,
            day_of_week=0,
            start_time=time(0, 0),
            end_time=time(23, 59, 59),
            is_working_day=True,
        )
    )
    db.commit()
    record_ids = provider.id, service.id
    db.close()

    try:
        yield record_ids
    finally:
        cleanup = SessionLocal()
        cleanup.execute(
            delete(AppointmentCancellation).where(
                AppointmentCancellation.appointment_id.in_(
                    select(Appointment.id).where(
                        Appointment.provider_id == record_ids[0]
                    )
                )
            )
        )
        cleanup.execute(
            delete(Appointment).where(Appointment.provider_id == record_ids[0])
        )
        cleanup.execute(
            delete(ProviderAvailability).where(
                ProviderAvailability.provider_id == record_ids[0]
            )
        )
        cleanup.execute(
            delete(ProviderService).where(ProviderService.provider_id == record_ids[0])
        )
        cleanup.execute(delete(Provider).where(Provider.id == record_ids[0]))
        cleanup.execute(delete(Service).where(Service.id == record_ids[1]))
        cleanup.commit()
        cleanup.close()


def next_monday_at_ten() -> datetime:
    days_until_monday = (7 - datetime.now(UTC).weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    return datetime.combine(
        datetime.now(UTC).date() + timedelta(days=days_until_monday),
        time(10, 0),
        tzinfo=UTC,
    )


def test_cancellation_releases_slot_and_records_history(cancellation_records):
    provider_id, service_id = cancellation_records
    appointment_start = next_monday_at_ten()
    db = SessionLocal()
    appointment = create_appointment(
        db,
        AppointmentCreate(
            service_id=service_id,
            provider_id=provider_id,
            user_name="Cancellation Test",
            user_email="cancellation-test@example.com",
            appointment_start=appointment_start,
        ),
    )
    db.close()

    db = SessionLocal()
    cancel_appointment_endpoint(
        appointment.id,
        db,
        AppointmentCancellationRequest(
            cancelled_by="customer",
            reason="No longer needed",
        ),
    )
    cancelled = db.get(Appointment, appointment.id)
    cancellation = db.scalar(
        select(AppointmentCancellation).where(
            AppointmentCancellation.appointment_id == appointment.id
        )
    )
    db.close()

    assert cancelled is not None
    assert cancelled.status == AppointmentStatus.CANCELLED
    assert cancellation is not None
    assert cancellation.cancelled_by == "customer"

    db = SessionLocal()
    replacement = create_appointment(
        db,
        AppointmentCreate(
            service_id=service_id,
            provider_id=provider_id,
            user_name="Replacement Customer",
            user_email="replacement@example.com",
            appointment_start=appointment_start,
        ),
    )
    db.close()
    assert replacement.id != appointment.id


def test_reschedule_updates_existing_appointment_without_cancellation(
    cancellation_records,
):
    provider_id, service_id = cancellation_records
    original_start = next_monday_at_ten()
    new_start = original_start + timedelta(hours=1)

    db = SessionLocal()
    appointment = create_appointment(
        db,
        AppointmentCreate(
            service_id=service_id,
            provider_id=provider_id,
            user_name="Reschedule Test",
            user_email="reschedule-test@example.com",
            appointment_start=original_start,
        ),
    )
    appointment_id = appointment.id

    updated = reschedule_appointment(
        db,
        appointment_id,
        AppointmentRescheduleCreate(
            appointment_start=new_start,
            cancelled_by="customer",
            reason="Changed plans",
        ),
    )
    cancellation = db.scalar(
        select(AppointmentCancellation).where(
            AppointmentCancellation.appointment_id == appointment_id
        )
    )
    appointments = db.scalars(
        select(Appointment).where(Appointment.provider_id == provider_id)
    ).all()
    db.close()

    assert updated.id == appointment_id
    assert updated.status != AppointmentStatus.CANCELLED
    assert updated.appointment_start == new_start
    assert cancellation is None
    assert len(appointments) == 1


def test_cancellation_enforces_grace_period(cancellation_records, monkeypatch):
    provider_id, service_id = cancellation_records
    appointment_start = datetime.now(UTC) + timedelta(
        minutes=settings.cancellation_grace_period_minutes - 1
    )
    db = SessionLocal()
    appointment = Appointment(
        service_id=service_id,
        provider_id=provider_id,
        user_name="Grace Period Test",
        user_email="grace-period@example.com",
        appointment_start=appointment_start,
        appointment_end=appointment_start + timedelta(minutes=30),
        duration_minutes=30,
        status=AppointmentStatus.PENDING,
    )
    db.add(appointment)
    db.commit()
    appointment_id = appointment.id
    db.close()

    db = SessionLocal()
    with pytest.raises(HTTPException, match="grace period"):
        cancel_appointment_endpoint(appointment_id, db)
    db.rollback()
    db.close()
    monkeypatch.undo()


def test_booking_rejects_past_date(cancellation_records):
    provider_id, service_id = cancellation_records

    past_start = datetime.now(UTC) - timedelta(days=1)

    db = SessionLocal()

    with pytest.raises(
        BookingValidationError,
        match="Appointments cannot be booked in the past",
    ):
        create_appointment(
            db,
            AppointmentCreate(
                service_id=service_id,
                provider_id=provider_id,
                user_name="Past Date Test",
                user_email="past-date@example.com",
                appointment_start=past_start,
            ),
        )

    db.rollback()
    db.close()


def test_booking_rejects_outside_working_hours(cancellation_records):
    provider_id, service_id = cancellation_records

    next_monday = next_monday_at_ten().date()
    outside_hours_start = datetime.combine(
        next_monday,
        time(18, 0),
        tzinfo=UTC,
    )

    db = SessionLocal()

    provider = db.get(Provider, provider_id)
    service = db.get(Service, service_id)

    provider.availability[0].start_time = time(9, 0)
    provider.availability[0].end_time = time(17, 0)
    db.commit()

    with pytest.raises(
        BookingValidationError,
        match="Appointment is outside working hours",
    ):
        _validate_slot(
            db,
            outside_hours_start,
            service.duration_minutes,
            provider,
        )

    db.rollback()
    db.close()


def test_completed_appointment_cannot_be_cancelled(cancellation_records):
    provider_id, service_id = cancellation_records
    appointment_start = next_monday_at_ten()

    db = SessionLocal()

    appointment = create_appointment(
        db,
        AppointmentCreate(
            service_id=service_id,
            provider_id=provider_id,
            user_name="Completed Appointment Test",
            user_email="completed@example.com",
            appointment_start=appointment_start,
        ),
    )

    appointment.status = AppointmentStatus.COMPLETED
    db.commit()
    appointment_id = appointment.id
    db.close()

    db = SessionLocal()

    with pytest.raises(
        HTTPException, match="Completed appointments cannot be cancelled"
    ):
        cancel_appointment_endpoint(
            appointment_id,
            db,
            AppointmentCancellationRequest(
                cancelled_by="customer",
                reason="Testing completed cancellation",
            ),
        )

    db.rollback()
    db.close()
