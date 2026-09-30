from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.security import create_access_token
from app.db.database import SessionLocal
from app.main import app
from app.models.appointment import Appointment, AppointmentStatus
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.review import Review
from app.models.service import Service, ServiceStatus
from app.models.user import User, UserRole

client = TestClient(app)


@pytest.fixture
def review_api_records():
    db = SessionLocal()
    customer = User(
        name="Review API Customer",
        email=f"review-api-customer-{uuid4()}@example.com",
        password_hash="not-used",
        role=UserRole.CUSTOMER,
    )
    other_customer = User(
        name="Other Review API Customer",
        email=f"review-api-other-{uuid4()}@example.com",
        password_hash="not-used",
        role=UserRole.CUSTOMER,
    )
    service = Service(
        name=f"Review API Service {uuid4()}",
        description="Review API test service",
        duration_minutes=30,
        category="Testing",
        capacity=1,
        buffer_time_minutes=0,
        status=ServiceStatus.ACTIVE,
    )
    person = Provider(
        name=f"Reviewable Person {uuid4()}",
        type=ProviderType.PERSON,
        email=f"review-person-{uuid4()}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    resource = Provider(
        name=f"Unreviewable Resource {uuid4()}",
        type=ProviderType.RESOURCE,
        email=f"review-resource-{uuid4()}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    db.add_all([customer, other_customer, service, person, resource])
    db.flush()

    base_start = datetime.now(UTC) - timedelta(days=2)

    def add_appointment(provider, owner, appointment_status, index):
        appointment = Appointment(
            service_id=service.id,
            provider_id=provider.id,
            customer_id=owner.id,
            user_name=owner.name,
            user_email=owner.email,
            appointment_start=base_start + timedelta(hours=index),
            appointment_end=base_start + timedelta(hours=index, minutes=30),
            duration_minutes=30,
            status=appointment_status,
        )
        db.add(appointment)
        db.flush()
        return appointment

    person_completed = add_appointment(person, customer, AppointmentStatus.COMPLETED, 0)
    resource_completed = add_appointment(
        resource, customer, AppointmentStatus.COMPLETED, 1
    )
    person_pending = add_appointment(person, customer, AppointmentStatus.CONFIRMED, 2)
    another_customers_completed = add_appointment(
        person, other_customer, AppointmentStatus.COMPLETED, 3
    )

    db.commit()
    records = {
        "customer_id": customer.id,
        "customer_role": customer.role,
        "other_customer_id": other_customer.id,
        "person_provider_id": person.id,
        "resource_provider_id": resource.id,
        "appointments": {
            "person_completed": person_completed.id,
            "resource_completed": resource_completed.id,
            "person_pending": person_pending.id,
            "other_customer_completed": another_customers_completed.id,
        },
        "appointment_ids": [
            person_completed.id,
            resource_completed.id,
            person_pending.id,
            another_customers_completed.id,
        ],
        "user_ids": [customer.id, other_customer.id],
        "provider_ids": [person.id, resource.id],
        "service_id": service.id,
    }
    db.close()

    try:
        yield records
    finally:
        cleanup = SessionLocal()
        appointment_ids = records["appointment_ids"]
        cleanup.execute(
            delete(Review).where(Review.appointment_id.in_(appointment_ids))
        )
        cleanup.execute(delete(Appointment).where(Appointment.id.in_(appointment_ids)))
        cleanup.execute(
            delete(Provider).where(Provider.id.in_(records["provider_ids"]))
        )
        cleanup.execute(delete(Service).where(Service.id == records["service_id"]))
        cleanup.execute(delete(User).where(User.id.in_(records["user_ids"])))
        cleanup.commit()
        cleanup.close()


def _customer_headers(records):
    token = create_access_token(records["customer_id"], records["customer_role"])
    return {"Authorization": f"Bearer {token}"}


def test_completed_person_appointment_can_be_reviewed(review_api_records):
    records = review_api_records
    appointment_id = records["appointments"]["person_completed"]
    response = client.post(
        "/api/reviews",
        headers=_customer_headers(records),
        json={
            "appointment_id": str(appointment_id),
            "rating": 5,
            "comment": "Helpful consultation",
            "customer_id": str(records["other_customer_id"]),
            "provider_id": str(records["resource_provider_id"]),
        },
    )
    assert response.status_code == 422

    response = client.post(
        "/api/reviews",
        headers=_customer_headers(records),
        json={
            "appointment_id": str(appointment_id),
            "rating": 5,
            "comment": "Helpful consultation",
        },
    )

    assert response.status_code == 201
    review = response.json()
    assert review["appointment_id"] == str(appointment_id)

    db = SessionLocal()
    saved_review = db.get(Review, UUID(review["id"]))
    assert saved_review.customer_id == records["customer_id"]
    assert saved_review.provider_id == records["person_provider_id"]
    db.close()


def test_completed_resource_appointment_cannot_be_reviewed(review_api_records):
    records = review_api_records
    appointment_id = records["appointments"]["resource_completed"]

    response = client.post(
        "/api/reviews",
        headers=_customer_headers(records),
        json={"appointment_id": str(appointment_id), "rating": 4},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only person providers can be reviewed"

    db = SessionLocal()
    review_count = db.query(Review).filter_by(appointment_id=appointment_id).count()
    db.close()
    assert review_count == 0


def test_review_creation_keeps_ownership_and_completion_checks(review_api_records):
    records = review_api_records
    headers = _customer_headers(records)

    wrong_owner_response = client.post(
        "/api/reviews",
        headers=headers,
        json={
            "appointment_id": str(records["appointments"]["other_customer_completed"]),
            "rating": 5,
        },
    )
    incomplete_response = client.post(
        "/api/reviews",
        headers=headers,
        json={
            "appointment_id": str(records["appointments"]["person_pending"]),
            "rating": 5,
        },
    )

    assert wrong_owner_response.status_code == 403
    assert incomplete_response.status_code == 400
    assert (
        incomplete_response.json()["detail"]
        == "Only completed appointments can be reviewed"
    )


def test_existing_resource_reviews_cannot_be_read_or_updated(review_api_records):
    records = review_api_records
    appointment_id = records["appointments"]["resource_completed"]
    db = SessionLocal()
    resource_review = Review(
        appointment_id=appointment_id,
        customer_id=records["customer_id"],
        provider_id=records["resource_provider_id"],
        rating=4,
    )
    db.add(resource_review)
    db.commit()
    review_id = resource_review.id
    db.close()

    headers = _customer_headers(records)
    read_response = client.get(
        f"/api/reviews/appointment/{appointment_id}", headers=headers
    )
    update_response = client.put(
        f"/api/reviews/{review_id}",
        headers=headers,
        json={"rating": 5, "comment": "Should remain inaccessible"},
    )

    assert read_response.status_code == 400
    assert update_response.status_code == 400
