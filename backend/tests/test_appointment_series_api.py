from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError

from app.core.security import create_access_token
from app.db.database import SessionLocal, get_db
from app.main import app
from app.models.appointment import Appointment, AppointmentStatus
from app.models.appointment_series import AppointmentSeries
from app.models.availability import ProviderAvailability
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.service import Service, ServiceStatus
from app.models.user import User, UserRole

client = TestClient(app)


@pytest.fixture
def series_records(monkeypatch):
    monkeypatch.setattr(
        "app.services.appointment_series.enqueue_confirmation_notification",
        lambda _appointment: None,
    )
    monkeypatch.setattr(
        "app.services.appointment_series.schedule_appointment_notifications",
        lambda _appointment: None,
    )

    db = SessionLocal()
    customer = User(
        name="Series Customer",
        email=f"series-customer-{uuid4()}@example.com",
        password_hash="not-used",
        role=UserRole.CUSTOMER,
    )
    provider_user = User(
        name="Series Provider User",
        email=f"series-provider-user-{uuid4()}@example.com",
        password_hash="not-used",
        role=UserRole.PROVIDER,
    )
    provider = Provider(
        name=f"Series Provider {uuid4()}",
        type=ProviderType.PERSON,
        email=f"series-provider-{uuid4()}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    service = Service(
        name=f"Series Service {uuid4()}",
        description="Recurring test service",
        duration_minutes=30,
        category="Testing",
        capacity=1,
        buffer_time_minutes=10,
        status=ServiceStatus.ACTIVE,
    )
    db.add_all([customer, provider_user, provider, service])
    db.flush()
    db.add(
        ProviderService(
            provider_id=provider.id,
            service_id=service.id,
            is_active=True,
        )
    )
    db.add_all(
        ProviderAvailability(
            provider_id=provider.id,
            day_of_week=weekday,
            start_time=time(0),
            end_time=time(23, 59, 59),
            is_working_day=True,
        )
        for weekday in range(7)
    )
    db.commit()
    records = {
        "customer_id": customer.id,
        "customer_role": customer.role,
        "provider_user_id": provider_user.id,
        "provider_user_role": provider_user.role,
        "provider_id": provider.id,
        "service_id": service.id,
        "user_ids": [customer.id, provider_user.id],
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
        cleanup.execute(
            delete(ProviderAvailability).where(
                ProviderAvailability.provider_id == records["provider_id"]
            )
        )
        cleanup.execute(
            delete(ProviderService).where(
                ProviderService.provider_id == records["provider_id"]
            )
        )
        cleanup.execute(delete(Provider).where(Provider.id == records["provider_id"]))
        cleanup.execute(delete(Service).where(Service.id == records["service_id"]))
        cleanup.execute(delete(User).where(User.id.in_(records["user_ids"])))
        cleanup.commit()
        cleanup.close()


def _headers(records, role="customer"):
    if role == "provider":
        user_id = records["provider_user_id"]
        user_role = records["provider_user_role"]
    else:
        user_id = records["customer_id"]
        user_role = records["customer_role"]
    token = create_access_token(user_id, user_role)
    return {"Authorization": f"Bearer {token}"}


def _future_start_date(days=14):
    return (date.today() + timedelta(days=days)).isoformat()


def _request_body(records, **overrides):
    body = {
        "service_id": str(records["service_id"]),
        "provider_id": str(records["provider_id"]),
        "start_date": _future_start_date(),
        "local_start_time": "10:00:00",
        "frequency": "WEEKLY",
        "interval": 1,
        "end_mode": "COUNT",
        "occurrence_count": 3,
        "user_name": "Recurring Customer",
        "user_email": f"recurring-{uuid4()}@example.com",
        "user_phone": "555-0100",
        "notes": "Recurring appointment note",
    }
    body.update(overrides)
    return body


def _count_records(model, provider_id):
    with SessionLocal() as db:
        return db.scalar(
            select(func.count())
            .select_from(model)
            .where(model.provider_id == provider_id)
        )


def test_authenticated_customer_creates_atomic_series(series_records, monkeypatch):
    observed_notifications = []

    def notification_spy(appointment):
        with SessionLocal() as verify_db:
            assert verify_db.get(Appointment, appointment.id) is not None
        observed_notifications.append(appointment.id)

    monkeypatch.setattr(
        "app.services.appointment_series.enqueue_confirmation_notification",
        notification_spy,
    )
    monkeypatch.setattr(
        "app.services.appointment_series.schedule_appointment_notifications",
        notification_spy,
    )

    db = SessionLocal()
    original_commit = db.commit
    commit_count = 0

    def counted_commit():
        nonlocal commit_count
        commit_count += 1
        original_commit()

    db.commit = counted_commit

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.post(
            "/api/appointment-series",
            headers=_headers(series_records),
            json=_request_body(series_records),
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["provider_id"] == str(series_records["provider_id"])
    assert result["service_id"] == str(series_records["service_id"])
    assert result["timezone"] == "UTC"
    assert result["frequency"] == "weekly"
    assert result["status"] == "active"
    assert len(result["occurrences"]) == 3
    assert [item["occurrence_number"] for item in result["occurrences"]] == [
        1,
        2,
        3,
    ]
    assert all(item["status"] == "confirmed" for item in result["occurrences"])
    assert commit_count == 1
    assert len(observed_notifications) == 6

    with SessionLocal() as verify_db:
        series = verify_db.get(AppointmentSeries, result["id"])
        appointments = verify_db.scalars(
            select(Appointment)
            .where(Appointment.series_id == series.id)
            .order_by(Appointment.occurrence_number)
        ).all()
        assert series.customer_id == series_records["customer_id"]
        assert series.timezone == "UTC"
        assert len(appointments) == 3
        assert [item.occurrence_number for item in appointments] == [1, 2, 3]
        assert len({item.occurrence_number for item in appointments}) == 3
        assert all(
            item.customer_id == series_records["customer_id"] for item in appointments
        )
        assert all(item.buffer_time_minutes == 10 for item in appointments)
        assert all(item.user_name == "Recurring Customer" for item in appointments)
        assert all(item.user_phone == "555-0100" for item in appointments)
        assert all(item.notes == "Recurring appointment note" for item in appointments)


def test_unauthenticated_and_non_customer_users_are_rejected(series_records):
    body = _request_body(series_records)
    unauthenticated = client.post("/api/appointment-series", json=body)
    provider = client.post(
        "/api/appointment-series",
        headers=_headers(series_records, role="provider"),
        json=body,
    )

    assert unauthenticated.status_code == 401
    assert provider.status_code == 403
    assert _count_records(AppointmentSeries, series_records["provider_id"]) == 0


def test_invalid_service_provider_relationship_is_rejected(series_records):
    response = client.post(
        "/api/appointment-series",
        headers=_headers(series_records),
        json=_request_body(series_records, service_id=str(uuid4())),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Active service is not offered by provider"
    assert _count_records(AppointmentSeries, series_records["provider_id"]) == 0


@pytest.mark.parametrize(
    ("interval", "expected_days"),
    [(1, [0, 7, 14]), (2, [0, 14, 28])],
)
def test_weekly_intervals_create_expected_occurrences(
    series_records, interval, expected_days
):
    start_date = date.today() + timedelta(days=14)
    response = client.post(
        "/api/appointment-series",
        headers=_headers(series_records),
        json=_request_body(
            series_records,
            start_date=start_date.isoformat(),
            interval=interval,
        ),
    )

    assert response.status_code == 201, response.text
    starts = [
        datetime.fromisoformat(item["appointment_start"])
        for item in response.json()["occurrences"]
    ]
    assert [(item.date() - start_date).days for item in starts] == expected_days


def test_monthly_end_date_is_inclusive_and_preserves_anchor(series_records):
    response = client.post(
        "/api/appointment-series",
        headers=_headers(series_records),
        json=_request_body(
            series_records,
            start_date="2027-01-31",
            frequency="MONTHLY",
            end_mode="END_DATE",
            occurrence_count=None,
            end_date="2027-03-31",
        ),
    )

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["end_mode"] == "end_date"
    assert result["occurrence_count"] is None
    assert [
        datetime.fromisoformat(item["appointment_start"]).date().isoformat()
        for item in result["occurrences"]
    ] == ["2027-01-31", "2027-02-28", "2027-03-31"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"occurrence_count": None},
        {"end_mode": "END_DATE", "occurrence_count": None},
        {"end_date": "2027-01-01"},
        {"occurrence_count": 53},
        {"interval": 3},
        {"frequency": "MONTHLY", "interval": 2},
        {"frequency": "DAILY"},
        {"timezone": "Pacific/Auckland"},
        {"customer_id": str(uuid4())},
    ],
)
def test_invalid_recurrence_requests_are_rejected(series_records, overrides):
    response = client.post(
        "/api/appointment-series",
        headers=_headers(series_records),
        json=_request_body(series_records, **overrides),
    )

    assert response.status_code == 422
    assert _count_records(AppointmentSeries, series_records["provider_id"]) == 0


def test_end_date_without_end_date_is_rejected(series_records):
    response = client.post(
        "/api/appointment-series",
        headers=_headers(series_records),
        json=_request_body(
            series_records,
            end_mode="END_DATE",
            occurrence_count=None,
        ),
    )

    assert response.status_code == 422


def test_unavailable_occurrence_rolls_back_entire_series(series_records, monkeypatch):
    start_date = date.today() + timedelta(days=14)
    blocked_date = start_date + timedelta(days=7)
    existing_start = datetime.combine(blocked_date, time(10), tzinfo=UTC)
    db = SessionLocal()
    db.add(
        Appointment(
            provider_id=series_records["provider_id"],
            service_id=series_records["service_id"],
            user_name="Existing booking",
            user_email=f"existing-{uuid4()}@example.com",
            appointment_start=existing_start,
            appointment_end=existing_start + timedelta(minutes=30),
            duration_minutes=30,
            buffer_time_minutes=10,
            status=AppointmentStatus.CONFIRMED,
        )
    )
    db.commit()
    db.close()

    notifications = []
    monkeypatch.setattr(
        "app.services.appointment_series.enqueue_confirmation_notification",
        lambda appointment: notifications.append(appointment.id),
    )
    monkeypatch.setattr(
        "app.services.appointment_series.schedule_appointment_notifications",
        lambda appointment: notifications.append(appointment.id),
    )
    response = client.post(
        "/api/appointment-series",
        headers=_headers(series_records),
        json=_request_body(series_records, start_date=start_date.isoformat()),
    )

    assert response.status_code == 409
    conflicts = response.json()["detail"]["conflicts"]
    assert any(
        conflict["occurrence_number"] == 2
        and conflict["date"] == blocked_date.isoformat()
        for conflict in conflicts
    )
    assert _count_records(AppointmentSeries, series_records["provider_id"]) == 0
    assert _count_records(Appointment, series_records["provider_id"]) == 1
    assert notifications == []


def test_existing_appointment_buffer_snapshot_blocks_occurrence(series_records):
    start_date = date.today() + timedelta(days=14)
    existing_start = datetime.combine(start_date, time(10), tzinfo=UTC)
    db = SessionLocal()
    db.add(
        Appointment(
            provider_id=series_records["provider_id"],
            service_id=series_records["service_id"],
            user_name="Existing booking",
            user_email=f"existing-buffer-{uuid4()}@example.com",
            appointment_start=existing_start,
            appointment_end=existing_start + timedelta(minutes=30),
            duration_minutes=30,
            buffer_time_minutes=40,
            status=AppointmentStatus.CONFIRMED,
        )
    )
    db.commit()
    db.close()

    response = client.post(
        "/api/appointment-series",
        headers=_headers(series_records),
        json=_request_body(
            series_records,
            start_date=start_date.isoformat(),
            local_start_time="10:40:00",
            occurrence_count=1,
        ),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["conflicts"][0]["occurrence_number"] == 1
    assert _count_records(AppointmentSeries, series_records["provider_id"]) == 0


def test_candidate_service_buffer_blocks_later_existing_appointment(series_records):
    start_date = date.today() + timedelta(days=14)
    later_start = datetime.combine(start_date, time(10, 35), tzinfo=UTC)
    db = SessionLocal()
    db.add(
        Appointment(
            provider_id=series_records["provider_id"],
            service_id=series_records["service_id"],
            user_name="Later booking",
            user_email=f"later-{uuid4()}@example.com",
            appointment_start=later_start,
            appointment_end=later_start + timedelta(minutes=30),
            duration_minutes=30,
            buffer_time_minutes=0,
            status=AppointmentStatus.CONFIRMED,
        )
    )
    db.commit()
    db.close()

    response = client.post(
        "/api/appointment-series",
        headers=_headers(series_records),
        json=_request_body(
            series_records,
            start_date=start_date.isoformat(),
            local_start_time="10:00:00",
            occurrence_count=1,
        ),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["conflicts"][0]["occurrence_number"] == 1
    assert _count_records(AppointmentSeries, series_records["provider_id"]) == 0


def test_provider_timezone_snapshot_and_dst_validation(series_records):
    db = SessionLocal()
    provider = db.get(Provider, series_records["provider_id"])
    provider.timezone = "America/New_York"
    db.commit()
    db.close()

    nonexistent = client.post(
        "/api/appointment-series",
        headers=_headers(series_records),
        json=_request_body(
            series_records,
            start_date="2027-03-14",
            local_start_time="02:30:00",
            occurrence_count=1,
        ),
    )
    assert nonexistent.status_code == 422
    assert "does not exist" in nonexistent.json()["detail"]
    assert _count_records(AppointmentSeries, series_records["provider_id"]) == 0

    ambiguous = client.post(
        "/api/appointment-series",
        headers=_headers(series_records),
        json=_request_body(
            series_records,
            start_date="2026-11-01",
            local_start_time="01:30:00",
            occurrence_count=1,
        ),
    )
    assert ambiguous.status_code == 201, ambiguous.text
    result = ambiguous.json()
    assert result["timezone"] == "America/New_York"
    assert result["occurrences"][0]["appointment_start"] == "2026-11-01T05:30:00Z"


def test_end_date_recurrence_over_52_occurrences_is_rejected(series_records):
    response = client.post(
        "/api/appointment-series",
        headers=_headers(series_records),
        json=_request_body(
            series_records,
            start_date="2027-01-04",
            end_mode="END_DATE",
            occurrence_count=None,
            end_date="2028-01-10",
        ),
    )

    assert response.status_code == 422
    assert "52 occurrences" in response.json()["detail"]
    assert _count_records(AppointmentSeries, series_records["provider_id"]) == 0


def test_database_failure_rolls_back_without_leaking_or_notifying(
    series_records, monkeypatch
):
    notifications = []
    monkeypatch.setattr(
        "app.services.appointment_series.enqueue_confirmation_notification",
        lambda appointment: notifications.append(appointment.id),
    )
    monkeypatch.setattr(
        "app.services.appointment_series.schedule_appointment_notifications",
        lambda appointment: notifications.append(appointment.id),
    )
    db = SessionLocal()

    def fail_commit():
        raise OperationalError("commit", {}, RuntimeError("private database detail"))

    db.commit = fail_commit

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.post(
            "/api/appointment-series",
            headers=_headers(series_records),
            json=_request_body(series_records),
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()

    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to create appointment series"
    assert "private database detail" not in response.text
    assert notifications == []
    assert _count_records(AppointmentSeries, series_records["provider_id"]) == 0
    assert _count_records(Appointment, series_records["provider_id"]) == 0
