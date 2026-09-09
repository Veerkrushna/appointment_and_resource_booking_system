import threading
from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.db.database import SessionLocal
from app.models.appointment import Appointment
from app.models.availability import ProviderAvailability
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.service import Service, ServiceStatus
from app.schemas.appointment import AppointmentCreate
from app.services.booking import BookingConflictError, create_appointment


@pytest.fixture
def booking_records():
    db = SessionLocal()
    provider = Provider(
        name=f"Concurrency Provider {uuid4()}",
        type=ProviderType.PERSON,
        email=f"provider-{uuid4()}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    service = Service(
        name=f"Concurrency Service {uuid4()}",
        description="Concurrency test service",
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


def test_concurrent_bookings_allow_only_one_success(booking_records):
    provider_id, service_id = booking_records
    days_until_monday = (7 - datetime.now(UTC).weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    appointment_start = datetime.combine(
        datetime.now(UTC).date() + timedelta(days=days_until_monday),
        time(10, 0),
        tzinfo=UTC,
    )
    payloads = [
        AppointmentCreate(
            service_id=service_id,
            provider_id=provider_id,
            user_name="Concurrency Test One",
            user_email="concurrency-one@example.com",
            appointment_start=appointment_start,
        ),
        AppointmentCreate(
            service_id=service_id,
            provider_id=provider_id,
            user_name="Concurrency Test Two",
            user_email="concurrency-two@example.com",
            appointment_start=appointment_start,
        ),
    ]
    barrier = threading.Barrier(2)
    results: list[tuple[str, object] | None] = [None, None]

    def book(index: int, payload: AppointmentCreate) -> None:
        db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            appointment = create_appointment(db, payload)
            results[index] = ("success", appointment.id)
        except BookingConflictError as error:
            results[index] = ("conflict", error)
        except Exception as error:
            results[index] = ("error", error)
        finally:
            db.rollback()
            db.close()

    threads = [
        threading.Thread(target=book, args=(index, payload))
        for index, payload in enumerate(payloads)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert all(not thread.is_alive() for thread in threads)
    completed_results = [result for result in results if result is not None]
    assert sorted(result[0] for result in completed_results) == [
        "conflict",
        "success",
    ]
    assert all(result[0] != "error" for result in completed_results), results

    verification_db = SessionLocal()
    appointment_count = verification_db.scalar(
        select(func.count())
        .select_from(Appointment)
        .where(Appointment.provider_id == provider_id)
    )
    verification_db.close()
    assert appointment_count == 1
