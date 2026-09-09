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
from app.schemas.appointment import AppointmentCancellationRequest, AppointmentCreate
from app.services.booking import (
    create_appointment,
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
