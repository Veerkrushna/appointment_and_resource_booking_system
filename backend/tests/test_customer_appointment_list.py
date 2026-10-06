from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.security import create_access_token
from app.db.database import SessionLocal
from app.main import app
from app.models.appointment import Appointment, AppointmentStatus
from app.models.appointment_series import (
    AppointmentSeries,
    AppointmentSeriesEndMode,
    AppointmentSeriesFrequency,
)
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.service import Service, ServiceStatus
from app.models.user import User, UserRole

client = TestClient(app)


@pytest.fixture
def appointment_list_records():
    db = SessionLocal()
    customer = User(
        name="List Customer",
        email=f"list-customer-{uuid4()}@example.com",
        password_hash="not-used",
        role=UserRole.CUSTOMER,
    )
    other_customer = User(
        name="Other List Customer",
        email=f"other-list-customer-{uuid4()}@example.com",
        password_hash="not-used",
        role=UserRole.CUSTOMER,
    )
    provider_user = User(
        name="List Provider User",
        email=f"list-provider-user-{uuid4()}@example.com",
        password_hash="not-used",
        role=UserRole.PROVIDER,
    )
    admin_user = User(
        name="List Admin User",
        email=f"list-admin-user-{uuid4()}@example.com",
        password_hash="not-used",
        role=UserRole.ADMIN,
    )
    provider = Provider(
        name=f"List Provider {uuid4()}",
        type=ProviderType.PERSON,
        email=f"list-provider-{uuid4()}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    service = Service(
        name=f"List Service {uuid4()}",
        description="Customer appointment-list test service",
        duration_minutes=30,
        category="Testing",
        capacity=1,
        buffer_time_minutes=0,
        status=ServiceStatus.ACTIVE,
    )
    db.add_all([customer, other_customer, provider_user, admin_user, provider, service])
    db.commit()
    records = {
        "customer_id": customer.id,
        "other_customer_id": other_customer.id,
        "provider_user_id": provider_user.id,
        "admin_user_id": admin_user.id,
        "provider_id": provider.id,
        "service_id": service.id,
        "user_ids": [customer.id, other_customer.id, provider_user.id, admin_user.id],
    }
    db.close()

    try:
        yield records
    finally:
        cleanup = SessionLocal()
        cleanup.execute(
            delete(Appointment).where(Appointment.provider_id == records["provider_id"])
        )
        cleanup.execute(
            delete(AppointmentSeries).where(
                AppointmentSeries.provider_id == records["provider_id"]
            )
        )
        cleanup.execute(delete(Provider).where(Provider.id == records["provider_id"]))
        cleanup.execute(delete(Service).where(Service.id == records["service_id"]))
        cleanup.execute(delete(User).where(User.id.in_(records["user_ids"])))
        cleanup.commit()
        cleanup.close()


def _headers(user_id, role):
    return {
        "Authorization": f"Bearer {create_access_token(user_id, role)}",
    }


def _appointment(
    records,
    customer_id,
    appointment_start,
    *,
    series_id=None,
    occurrence_number=None,
):
    return Appointment(
        service_id=records["service_id"],
        provider_id=records["provider_id"],
        customer_id=customer_id,
        series_id=series_id,
        occurrence_number=occurrence_number,
        user_name="List Test Customer",
        user_email=f"appointment-{uuid4()}@example.com",
        appointment_start=appointment_start,
        appointment_end=appointment_start + timedelta(minutes=30),
        duration_minutes=30,
        buffer_time_minutes=0,
        status=AppointmentStatus.CONFIRMED,
    )


def _series(db, records):
    series = AppointmentSeries(
        customer_id=records["customer_id"],
        provider_id=records["provider_id"],
        service_id=records["service_id"],
        frequency=AppointmentSeriesFrequency.WEEKLY,
        interval=1,
        start_date=datetime.now(UTC).date() + timedelta(days=7),
        local_start_time=datetime.now(UTC).time().replace(tzinfo=None),
        timezone="UTC",
        end_mode=AppointmentSeriesEndMode.COUNT,
        occurrence_count=3,
    )
    db.add(series)
    db.flush()
    return series


def test_one_time_customer_appointment_serializes_null_series_fields(
    appointment_list_records,
):
    records = appointment_list_records
    db = SessionLocal()
    appointment = _appointment(
        records,
        records["customer_id"],
        datetime.now(UTC) + timedelta(days=2),
    )
    db.add(appointment)
    db.commit()
    db.close()

    response = client.get(
        "/api/customer/appointments?timezone=UTC",
        headers=_headers(records["customer_id"], UserRole.CUSTOMER),
    )

    assert response.status_code == 200
    result = response.json()
    assert len(result["appointments"]) == 1
    assert result["appointments"][0]["series_id"] is None
    assert result["appointments"][0]["occurrence_number"] is None


def test_recurring_customer_appointment_serializes_series_linkage(
    appointment_list_records,
):
    records = appointment_list_records
    db = SessionLocal()
    series = _series(db, records)
    appointment = _appointment(
        records,
        records["customer_id"],
        datetime.now(UTC) + timedelta(days=2),
        series_id=series.id,
        occurrence_number=2,
    )
    db.add(appointment)
    db.commit()
    series_id = series.id
    db.close()

    response = client.get(
        "/api/customer/appointments?timezone=UTC",
        headers=_headers(records["customer_id"], UserRole.CUSTOMER),
    )

    assert response.status_code == 200
    item = response.json()["appointments"][0]
    assert item["series_id"] == str(series_id)
    assert item["occurrence_number"] == 2


def test_series_occurrences_keep_individual_occurrence_numbers(
    appointment_list_records,
):
    records = appointment_list_records
    db = SessionLocal()
    series = _series(db, records)
    start = datetime.now(UTC) + timedelta(days=2)
    db.add_all(
        [
            _appointment(
                records,
                records["customer_id"],
                start + timedelta(days=index),
                series_id=series.id,
                occurrence_number=occurrence_number,
            )
            for index, occurrence_number in enumerate((3, 1, 2))
        ]
    )
    series_id = series.id
    db.commit()
    db.close()

    response = client.get(
        "/api/customer/appointments?timezone=UTC",
        headers=_headers(records["customer_id"], UserRole.CUSTOMER),
    )

    assert response.status_code == 200
    items = response.json()["appointments"]
    assert [item["occurrence_number"] for item in items] == [3, 1, 2]
    assert all(item["series_id"] == str(series_id) for item in items)


def test_customer_appointment_list_pagination_order_and_ownership_are_unchanged(
    appointment_list_records,
):
    records = appointment_list_records
    start = datetime.now(UTC) + timedelta(days=1)
    db = SessionLocal()
    db.add_all(
        [
            _appointment(
                records,
                records["customer_id"],
                start + timedelta(days=index),
            )
            for index in range(17)
        ]
    )
    db.add(
        _appointment(
            records,
            records["other_customer_id"],
            start + timedelta(hours=1),
        )
    )
    db.commit()
    db.close()
    headers = _headers(records["customer_id"], UserRole.CUSTOMER)

    first_page = client.get("/api/customer/appointments?page=1", headers=headers)
    second_page = client.get("/api/customer/appointments?page=2", headers=headers)

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    first_result = first_page.json()
    second_result = second_page.json()
    assert len(first_result["appointments"]) == 15
    assert len(second_result["appointments"]) == 2
    assert first_result["total"] == second_result["total"] == 17
    assert first_result["total_pages"] == second_result["total_pages"] == 2
    all_starts = [
        item["appointment_start"]
        for item in first_result["appointments"] + second_result["appointments"]
    ]
    assert all_starts == sorted(all_starts)
    assert all(
        item["series_id"] is None and item["occurrence_number"] is None
        for item in first_result["appointments"] + second_result["appointments"]
    )


def test_customer_appointment_list_authorization_is_unchanged(
    appointment_list_records,
):
    records = appointment_list_records
    unauthenticated = client.get("/api/customer/appointments")
    provider = client.get(
        "/api/customer/appointments",
        headers=_headers(records["provider_user_id"], UserRole.PROVIDER),
    )
    admin = client.get(
        "/api/customer/appointments",
        headers=_headers(records["admin_user_id"], UserRole.ADMIN),
    )

    assert unauthenticated.status_code == 401
    assert provider.status_code == 200
    assert admin.status_code == 403
