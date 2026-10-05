from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from app.api.routes.appointments import book_appointment
from app.db.database import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.availability import ProviderAvailability
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.service import Service, ServiceStatus
from app.schemas.appointment import AppointmentCreate, AppointmentRescheduleCreate
from app.services.availability import calculate_available_slots
from app.services.booking import (
    BookingValidationError,
    create_appointment,
    reschedule_appointment,
)


@pytest.fixture
def buffer_records(monkeypatch):
    monkeypatch.setattr(
        "app.services.booking.enqueue_confirmation_notification",
        lambda _appointment: None,
    )
    monkeypatch.setattr(
        "app.services.booking.schedule_appointment_notifications",
        lambda _appointment: None,
    )
    monkeypatch.setattr(
        "app.services.booking.send_reschedule_notification.delay",
        lambda _appointment_id: None,
    )

    db = SessionLocal()
    provider = Provider(
        name=f"Buffer Provider {uuid4()}",
        type=ProviderType.PERSON,
        email=f"buffer-provider-{uuid4()}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    service_a = Service(
        name=f"Buffer Service A {uuid4()}",
        duration_minutes=30,
        category="Testing",
        capacity=1,
        buffer_time_minutes=10,
        status=ServiceStatus.ACTIVE,
    )
    service_b = Service(
        name=f"Buffer Service B {uuid4()}",
        duration_minutes=60,
        category="Testing",
        capacity=1,
        buffer_time_minutes=20,
        status=ServiceStatus.ACTIVE,
    )
    db.add_all([provider, service_a, service_b])
    db.flush()
    db.add_all(
        [
            ProviderService(
                provider_id=provider.id, service_id=service_a.id, is_active=True
            ),
            ProviderService(
                provider_id=provider.id, service_id=service_b.id, is_active=True
            ),
            ProviderAvailability(
                provider_id=provider.id,
                day_of_week=0,
                start_time=time(0, 0),
                end_time=time(23, 59, 59),
                is_working_day=True,
            ),
        ]
    )
    db.commit()
    days_until_monday = (7 - datetime.now(UTC).weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    monday = datetime.combine(
        datetime.now(UTC).date() + timedelta(days=days_until_monday),
        time.min,
        tzinfo=UTC,
    )
    record_ids = provider.id, service_a.id, service_b.id
    db.close()

    try:
        yield record_ids, monday
    finally:
        cleanup = SessionLocal()
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
        cleanup.execute(delete(Service).where(Service.id.in_(record_ids[1:])))
        cleanup.commit()
        cleanup.close()


def add_existing_appointment(db, provider_id, service_id, start, duration):
    appointment = Appointment(
        provider_id=provider_id,
        service_id=service_id,
        user_name="Existing Customer",
        user_email=f"existing-{uuid4()}@example.com",
        appointment_start=start,
        appointment_end=start + timedelta(minutes=duration),
        duration_minutes=duration,
        status=AppointmentStatus.CONFIRMED,
    )
    db.add(appointment)
    db.commit()
    return appointment


def availability_starts(db, provider_id, service_id, target_date):
    slots = calculate_available_slots(
        db,
        service_id,
        target_date,
        target_date,
        provider_id=provider_id,
        slot_interval_minutes=10,
    )
    return {slot.start for slot in slots or []}


def appointment_payload(provider_id, service_id, start):
    return AppointmentCreate(
        service_id=service_id,
        provider_id=provider_id,
        user_name="Candidate Customer",
        user_email=f"candidate-{uuid4()}@example.com",
        appointment_start=start,
    )


def test_existing_service_buffer_blocks_other_service_and_api_agrees(buffer_records):
    (provider_id, service_a_id, service_b_id), monday = buffer_records
    db = SessionLocal()
    add_existing_appointment(
        db, provider_id, service_a_id, monday + timedelta(hours=10), 30
    )

    unavailable_start = monday + timedelta(hours=10, minutes=30)
    assert unavailable_start not in availability_starts(
        db, provider_id, service_b_id, monday.date()
    )
    with pytest.raises(HTTPException) as error:
        book_appointment(
            appointment_payload(provider_id, service_b_id, unavailable_start),
            db,
            None,
            "UTC",
        )
    assert error.value.status_code == 409

    available_start = monday + timedelta(hours=10, minutes=40)
    assert available_start in availability_starts(
        db, provider_id, service_b_id, monday.date()
    )
    created = book_appointment(
        appointment_payload(provider_id, service_b_id, available_start),
        db,
        None,
        "UTC",
    )
    assert created.appointment_start == available_start
    db.close()


def test_existing_service_b_buffer_controls_different_service_booking(buffer_records):
    (provider_id, service_a_id, service_b_id), monday = buffer_records
    db = SessionLocal()
    add_existing_appointment(
        db, provider_id, service_b_id, monday + timedelta(hours=10), 60
    )

    blocked_start = monday + timedelta(hours=11)
    assert blocked_start not in availability_starts(
        db, provider_id, service_a_id, monday.date()
    )
    with pytest.raises(BookingValidationError, match="already booked"):
        create_appointment(
            db, appointment_payload(provider_id, service_a_id, blocked_start)
        )

    after_buffer_start = monday + timedelta(hours=11, minutes=20)
    assert after_buffer_start in availability_starts(
        db, provider_id, service_a_id, monday.date()
    )
    created = create_appointment(
        db, appointment_payload(provider_id, service_a_id, after_buffer_start)
    )
    assert created.appointment_start == after_buffer_start
    db.close()


def test_candidate_buffer_must_fit_before_later_appointment(buffer_records):
    (provider_id, service_a_id, service_b_id), monday = buffer_records
    db = SessionLocal()
    add_existing_appointment(
        db,
        provider_id,
        service_a_id,
        monday + timedelta(hours=11, minutes=50),
        30,
    )

    candidate_start = monday + timedelta(hours=10, minutes=40)
    assert candidate_start not in availability_starts(
        db, provider_id, service_b_id, monday.date()
    )
    with pytest.raises(BookingValidationError, match="already booked"):
        create_appointment(
            db, appointment_payload(provider_id, service_b_id, candidate_start)
        )
    db.close()


def test_null_existing_buffer_behaves_as_zero(buffer_records):
    (provider_id, service_a_id, service_b_id), monday = buffer_records
    db = SessionLocal()
    service_a = db.get(Service, service_a_id)
    service_a.buffer_time_minutes = None
    db.commit()
    add_existing_appointment(
        db, provider_id, service_a_id, monday + timedelta(hours=10), 30
    )

    candidate_start = monday + timedelta(hours=10, minutes=30)
    assert candidate_start in availability_starts(
        db, provider_id, service_b_id, monday.date()
    )
    created = create_appointment(
        db, appointment_payload(provider_id, service_b_id, candidate_start)
    )
    assert created.appointment_start == candidate_start
    db.close()


def test_reschedule_uses_existing_appointment_service_buffer(buffer_records):
    (provider_id, service_a_id, service_b_id), monday = buffer_records
    db = SessionLocal()
    add_existing_appointment(
        db, provider_id, service_a_id, monday + timedelta(hours=10), 30
    )
    rescheduled_appointment = create_appointment(
        db,
        appointment_payload(provider_id, service_b_id, monday + timedelta(hours=13)),
    )

    with pytest.raises(BookingValidationError, match="already booked"):
        reschedule_appointment(
            db,
            rescheduled_appointment.id,
            AppointmentRescheduleCreate(
                appointment_start=monday + timedelta(hours=10, minutes=30),
                cancelled_by="customer",
            ),
        )
    db.rollback()
    db.close()


def test_reschedule_does_not_conflict_with_own_appointment(buffer_records):
    (provider_id, service_a_id, _service_b_id), monday = buffer_records
    db = SessionLocal()
    start = monday + timedelta(hours=10)
    appointment = create_appointment(
        db,
        appointment_payload(provider_id, service_a_id, start),
    )

    rescheduled = reschedule_appointment(
        db,
        appointment.id,
        AppointmentRescheduleCreate(
            appointment_start=start,
            cancelled_by="customer",
        ),
    )

    assert rescheduled.id == appointment.id
    assert rescheduled.appointment_start == start
    assert rescheduled.appointment_end == start + timedelta(minutes=30)
    db.close()
