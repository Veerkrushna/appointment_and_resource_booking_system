from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.main import app
from app.models.appointment import Appointment, AppointmentStatus
from app.models.availability import ProviderAvailability
from app.models.provider_service import ProviderService
from app.models.providers import (
    AvailabilityStatus,
    Provider,
    ProviderType,
)
from app.models.review import Review
from app.models.service import Service, ServiceStatus
from app.models.user import User, UserRole

client = TestClient(app)


@pytest.fixture
def provider_rating_records():
    db = SessionLocal()
    customer = User(
        name="Provider Rating Test Customer",
        email=f"provider-rating-customer-{uuid4()}@example.com",
        password_hash="not-used",
        role=UserRole.CUSTOMER,
    )
    service = Service(
        name=f"Provider Rating Service {uuid4()}",
        description="Provider rating integration test",
        duration_minutes=30,
        category="Testing",
        capacity=1,
        buffer_time_minutes=0,
        status=ServiceStatus.ACTIVE,
    )
    provider_a = Provider(
        name=f"Rating Provider A {uuid4()}",
        type=ProviderType.PERSON,
        email=f"rating-provider-a-{uuid4()}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    provider_b = Provider(
        name=f"Rating Provider B {uuid4()}",
        type=ProviderType.PERSON,
        email=f"rating-provider-b-{uuid4()}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    unrated_provider = Provider(
        name=f"Unrated Provider {uuid4()}",
        type=ProviderType.PERSON,
        email=f"unrated-provider-{uuid4()}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    resource = Provider(
        name=f"Rating Resource {uuid4()}",
        type=ProviderType.RESOURCE,
        email=f"rating-resource-{uuid4()}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    providers = [provider_a, provider_b, unrated_provider, resource]
    db.add_all([customer, service, *providers])
    db.flush()

    for provider in providers:
        db.add(
            ProviderService(
                provider_id=provider.id,
                service_id=service.id,
                is_active=True,
            )
        )

    target_date = datetime.now(UTC).date() + timedelta(days=7)
    for provider in providers:
        db.add(
            ProviderAvailability(
                provider_id=provider.id,
                day_of_week=target_date.weekday(),
                start_time=time(9, 0),
                end_time=time(10, 0),
                is_working_day=True,
            )
        )

    review_sets = [
        (provider_a, [5, 4, 5]),
        (provider_b, [3, 3, 4]),
    ]
    appointment_start = datetime.now(UTC) - timedelta(days=7)
    for provider, ratings in review_sets:
        for index, rating in enumerate(ratings):
            appointment = Appointment(
                service_id=service.id,
                provider_id=provider.id,
                customer_id=customer.id,
                user_name=customer.name,
                user_email=customer.email,
                appointment_start=appointment_start + timedelta(hours=index),
                appointment_end=appointment_start + timedelta(hours=index, minutes=30),
                duration_minutes=30,
                status=AppointmentStatus.COMPLETED,
            )
            db.add(appointment)
            db.flush()
            db.add(
                Review(
                    appointment_id=appointment.id,
                    customer_id=customer.id,
                    provider_id=provider.id,
                    rating=rating,
                )
            )

    db.commit()
    customer_email = customer.email
    ids = {
        "service": service.id,
        "customer_email": customer_email,
        "providers": {
            "a": provider_a.id,
            "b": provider_b.id,
            "unrated": unrated_provider.id,
            "resource": resource.id,
        },
        "names": {provider.id: provider.name for provider in providers},
        "date": target_date.isoformat(),
    }
    db.close()

    try:
        yield ids
    finally:
        cleanup = SessionLocal()
        provider_ids = list(ids["providers"].values())
        cleanup.execute(delete(Review).where(Review.provider_id.in_(provider_ids)))
        cleanup.execute(
            delete(Appointment).where(Appointment.provider_id.in_(provider_ids))
        )
        cleanup.execute(
            delete(ProviderAvailability).where(
                ProviderAvailability.provider_id.in_(provider_ids)
            )
        )
        cleanup.execute(
            delete(ProviderService).where(ProviderService.provider_id.in_(provider_ids))
        )
        cleanup.execute(delete(Provider).where(Provider.id.in_(provider_ids)))
        cleanup.execute(delete(Service).where(Service.id == ids["service"]))
        cleanup.execute(delete(User).where(User.email == ids["customer_email"]))
        cleanup.commit()
        cleanup.close()


def test_provider_list_includes_grouped_rating_data(provider_rating_records):
    records = provider_rating_records
    response = client.get("/api/providers")

    assert response.status_code == 200
    providers = {item["id"]: item for item in response.json()}

    provider_a = providers[str(records["providers"]["a"])]
    assert provider_a["average_rating"] == 4.67
    assert provider_a["rating_count"] == 3

    provider_b = providers[str(records["providers"]["b"])]
    assert provider_b["average_rating"] == 3.33
    assert provider_b["rating_count"] == 3

    for provider_key in ("unrated", "resource"):
        provider = providers[str(records["providers"][provider_key])]
        assert provider["average_rating"] is None
        assert provider["rating_count"] == 0


def test_availability_slots_include_reused_provider_ratings(provider_rating_records):
    records = provider_rating_records
    response = client.get(
        "/api/availability/slots",
        params={
            "service_id": str(records["service"]),
            "start_date": records["date"],
            "end_date": records["date"],
        },
    )

    assert response.status_code == 200
    slots = response.json()["slots"]
    assert len(slots) > 3

    slots_by_provider = {}
    for slot in slots:
        slots_by_provider.setdefault(slot["provider_id"], []).append(slot)

    for provider_key, expected_average, expected_count in (
        ("a", 4.67, 3),
        ("b", 3.33, 3),
        ("unrated", None, 0),
        ("resource", None, 0),
    ):
        provider_id = str(records["providers"][provider_key])
        provider_slots = slots_by_provider[provider_id]
        assert len(provider_slots) > 1
        assert all(
            slot["provider_name"]
            == records["names"][records["providers"][provider_key]]
            for slot in provider_slots
        )
        assert all(
            slot["provider_average_rating"] == expected_average
            and slot["provider_rating_count"] == expected_count
            for slot in provider_slots
        )
