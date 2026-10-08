from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.database import SessionLocal
from app.main import app
from app.models.appointment import Appointment, AppointmentStatus
from app.models.availability import ProviderAvailability
from app.models.booking_hold import BookingHold, BookingHoldStatus
from app.models.payment import Payment, PaymentProvider, PaymentStatus
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.service import Service, ServiceStatus
from app.models.user import User, UserRole

client = TestClient(app)


@pytest.fixture
def verification_records():
    db = SessionLocal()
    suffix = uuid4()
    customer = User(
        name=f"Verification Customer {suffix}",
        email=f"verification-customer-{suffix}@example.com",
        phone="+15550001001",
        password_hash="test",
        role=UserRole.CUSTOMER,
    )
    other_customer = User(
        name=f"Other Verification Customer {suffix}",
        email=f"other-verification-customer-{suffix}@example.com",
        password_hash="test",
        role=UserRole.CUSTOMER,
    )
    provider_user = User(
        name=f"Verification Provider User {suffix}",
        email=f"verification-provider-user-{suffix}@example.com",
        password_hash="test",
        role=UserRole.PROVIDER,
    )
    provider = Provider(
        name=f"Verification Provider {suffix}",
        type=ProviderType.PERSON,
        email=f"verification-provider-{suffix}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    service = Service(
        name=f"Verification Service {suffix}",
        duration_minutes=30,
        category="Testing",
        capacity=1,
        buffer_time_minutes=10,
        price=Decimal("25.10"),
        status=ServiceStatus.ACTIVE,
    )
    db.add_all([customer, other_customer, provider_user, provider, service])
    db.flush()
    db.add(
        ProviderService(
            provider_id=provider.id,
            service_id=service.id,
            is_active=True,
        )
    )
    target_day = datetime.now(UTC).date() + timedelta(days=3)
    db.add(
        ProviderAvailability(
            provider_id=provider.id,
            day_of_week=target_day.weekday(),
            start_time=time(0, 0),
            end_time=time(23, 59),
            is_working_day=True,
        )
    )
    appointment_start = datetime.combine(target_day, time(10, 0), tzinfo=UTC)
    order_id = f"order_{uuid4().hex}"
    payment = Payment(
        customer_id=customer.id,
        amount=2510,
        currency="INR",
        status=PaymentStatus.CREATED,
        provider=PaymentProvider.RAZORPAY,
        provider_order_id=order_id,
    )
    db.add(payment)
    db.flush()
    hold = BookingHold(
        customer_id=customer.id,
        service_id=service.id,
        provider_id=provider.id,
        appointment_start=appointment_start,
        appointment_end=appointment_start + timedelta(minutes=30),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        status=BookingHoldStatus.ACTIVE,
        payment_id=payment.id,
    )
    db.add(hold)
    db.commit()

    records = {
        "customer_id": customer.id,
        "customer_token": create_access_token(customer.id, customer.role),
        "other_customer_token": create_access_token(
            other_customer.id, other_customer.role
        ),
        "provider_id": provider.id,
        "provider_token": create_access_token(provider_user.id, provider_user.role),
        "service_id": service.id,
        "payment_id": payment.id,
        "order_id": order_id,
        "payment_provider_id": f"pay_{uuid4().hex}",
        "signature": f"signature_{uuid4().hex}",
        "appointment_start": appointment_start,
    }
    db.close()
    try:
        yield records
    finally:
        cleanup = SessionLocal()
        cleanup.execute(delete(BookingHold).where(BookingHold.payment_id == payment.id))
        cleanup.execute(delete(Payment).where(Payment.id == payment.id))
        cleanup.execute(
            delete(Appointment).where(Appointment.provider_id == provider.id)
        )
        cleanup.execute(
            delete(ProviderAvailability).where(
                ProviderAvailability.provider_id == provider.id
            )
        )
        cleanup.execute(
            delete(ProviderService).where(ProviderService.provider_id == provider.id)
        )
        cleanup.execute(delete(Provider).where(Provider.id == provider.id))
        cleanup.execute(delete(Service).where(Service.id == service.id))
        cleanup.execute(
            delete(User).where(
                User.id.in_([customer.id, other_customer.id, provider_user.id])
            )
        )
        cleanup.commit()
        cleanup.close()


def _stub_verification(monkeypatch, result=True):
    calls = []

    class MockRazorpayService:
        def verify_payment(self, order_id, payment_id, signature):
            calls.append((order_id, payment_id, signature))
            return result

    monkeypatch.setattr(
        "app.services.payment_verification.RazorpayService", MockRazorpayService
    )
    return calls


def _verify_request(records, *, token=None, body=None):
    return client.post(
        "/api/payments/verify",
        headers={"Authorization": f"Bearer {token or records['customer_token']}"},
        json=body
        or {
            "payment_id": records["payment_provider_id"],
            "order_id": records["order_id"],
            "signature": records["signature"],
        },
    )


def _read_payment_state(records):
    db = SessionLocal()
    payment = db.get(Payment, records["payment_id"])
    hold = db.scalar(
        select(BookingHold).where(BookingHold.payment_id == records["payment_id"])
    )
    appointment_count = db.scalar(
        select(func.count())
        .select_from(Appointment)
        .where(Appointment.provider_id == records["provider_id"])
    )
    result = payment, hold, appointment_count
    db.close()
    return result


def test_valid_signature_captures_payment_and_converts_hold(
    verification_records, monkeypatch
):
    records = verification_records
    calls = _stub_verification(monkeypatch)

    response = _verify_request(records)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == PaymentStatus.CAPTURED
    assert data["appointment_status"] == AppointmentStatus.CONFIRMED
    assert data["order_id"] == records["order_id"]
    assert calls == [
        (
            records["order_id"],
            records["payment_provider_id"],
            records["signature"],
        )
    ]
    payment, hold, appointment_count = _read_payment_state(records)
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.provider_payment_id == records["payment_provider_id"]
    assert payment.provider_signature == records["signature"]
    assert str(payment.appointment_id) == data["appointment_id"]
    assert hold.status == BookingHoldStatus.CONVERTED
    assert appointment_count == 1


def test_invalid_signature_does_not_capture_payment(verification_records, monkeypatch):
    records = verification_records
    _stub_verification(monkeypatch, result=False)

    response = _verify_request(records)

    assert response.status_code == 400
    payment, hold, appointment_count = _read_payment_state(records)
    assert payment.status == PaymentStatus.CREATED
    assert payment.appointment_id is None
    assert hold.status == BookingHoldStatus.ACTIVE
    assert appointment_count == 0


@pytest.mark.parametrize(
    "body_change",
    [
        {"order_id": f"order_{uuid4().hex}"},
        {"payment_id": f"pay_{uuid4().hex}", "order_id": f"order_{uuid4().hex}"},
    ],
)
def test_wrong_or_unknown_order_is_rejected(
    verification_records, monkeypatch, body_change
):
    records = verification_records
    calls = _stub_verification(monkeypatch)
    body = {
        "payment_id": records["payment_provider_id"],
        "order_id": records["order_id"],
        "signature": records["signature"],
        **body_change,
    }

    response = _verify_request(records, body=body)

    assert response.status_code == 404
    assert calls == []
    payment, hold, appointment_count = _read_payment_state(records)
    assert payment.status == PaymentStatus.CREATED
    assert hold.status == BookingHoldStatus.ACTIVE
    assert appointment_count == 0


def test_payment_owned_by_another_customer_is_not_found(
    verification_records, monkeypatch
):
    records = verification_records
    calls = _stub_verification(monkeypatch)

    response = _verify_request(records, token=records["other_customer_token"])

    assert response.status_code == 404
    assert calls == []


def test_duplicate_verification_returns_existing_appointment(
    verification_records, monkeypatch
):
    records = verification_records
    calls = _stub_verification(monkeypatch)

    first = _verify_request(records)
    first_data = first.json()
    db = SessionLocal()
    appointment_before = db.get(Appointment, first_data["appointment_id"])
    appointment_snapshot = (
        appointment_before.status,
        appointment_before.appointment_start,
        appointment_before.appointment_end,
        appointment_before.duration_minutes,
        appointment_before.buffer_time_minutes,
        appointment_before.notes,
    )
    hold_count_before = db.scalar(
        select(func.count())
        .select_from(BookingHold)
        .where(BookingHold.payment_id == records["payment_id"])
    )
    db.get(Payment, records["payment_id"]).provider_signature = None
    db.commit()
    db.close()

    commits = []
    original_commit = Session.commit

    def track_commit(session):
        commits.append(session)
        return original_commit(session)

    monkeypatch.setattr(Session, "commit", track_commit)
    second = _verify_request(records)

    assert first.status_code == second.status_code == 200
    assert first_data["appointment_id"] == second.json()["appointment_id"]
    assert len(calls) == 1
    assert commits == []

    db = SessionLocal()
    appointment_after = db.get(Appointment, first_data["appointment_id"])
    assert appointment_snapshot == (
        appointment_after.status,
        appointment_after.appointment_start,
        appointment_after.appointment_end,
        appointment_after.duration_minutes,
        appointment_after.buffer_time_minutes,
        appointment_after.notes,
    )
    hold_count_after = db.scalar(
        select(func.count())
        .select_from(BookingHold)
        .where(BookingHold.payment_id == records["payment_id"])
    )
    assert hold_count_after == hold_count_before == 1
    db.close()
    assert _read_payment_state(records)[2] == 1


def test_expired_hold_is_marked_expired_without_capturing_payment(
    verification_records, monkeypatch
):
    records = verification_records
    _stub_verification(monkeypatch)
    db = SessionLocal()
    hold = db.scalar(
        select(BookingHold).where(BookingHold.payment_id == records["payment_id"])
    )
    hold.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    db.close()

    response = _verify_request(records)

    assert response.status_code == 409
    payment, hold, appointment_count = _read_payment_state(records)
    assert payment.status == PaymentStatus.CREATED
    assert hold.status == BookingHoldStatus.EXPIRED
    assert appointment_count == 0


def test_missing_hold_does_not_capture_payment(verification_records, monkeypatch):
    records = verification_records
    _stub_verification(monkeypatch)
    db = SessionLocal()
    db.execute(
        delete(BookingHold).where(BookingHold.payment_id == records["payment_id"])
    )
    db.commit()
    db.close()

    response = _verify_request(records)

    assert response.status_code == 409
    payment, hold, appointment_count = _read_payment_state(records)
    assert payment.status == PaymentStatus.CREATED
    assert hold is None
    assert appointment_count == 0


def test_appointment_creation_failure_rolls_back_payment_and_hold(
    verification_records, monkeypatch
):
    records = verification_records
    _stub_verification(monkeypatch)

    def fail_appointment_build(*_args, **_kwargs):
        raise RuntimeError("appointment build failed")

    monkeypatch.setattr(
        "app.services.payment_verification._build_held_appointment",
        fail_appointment_build,
    )
    with pytest.raises(RuntimeError, match="appointment build failed"):
        _verify_request(records)

    payment, hold, appointment_count = _read_payment_state(records)
    assert payment.status == PaymentStatus.CREATED
    assert payment.appointment_id is None
    assert hold.status == BookingHoldStatus.ACTIVE
    assert appointment_count == 0


def test_non_customer_cannot_verify_payment(verification_records, monkeypatch):
    records = verification_records
    calls = _stub_verification(monkeypatch)

    response = _verify_request(records, token=records["provider_token"])

    assert response.status_code == 403
    assert calls == []


def test_customer_id_is_not_accepted_in_verification_payload(
    verification_records, monkeypatch
):
    records = verification_records
    calls = _stub_verification(monkeypatch)
    body = {
        "payment_id": records["payment_provider_id"],
        "order_id": records["order_id"],
        "signature": records["signature"],
        "customer_id": str(records["customer_id"]),
    }

    response = _verify_request(records, body=body)

    assert response.status_code == 422
    assert calls == []


def test_notifications_are_triggered_only_after_successful_commit(
    verification_records, monkeypatch
):
    records = verification_records
    _stub_verification(monkeypatch)
    callbacks = []

    def assert_committed(appointment):
        db = SessionLocal()
        payment = db.get(Payment, records["payment_id"])
        hold = db.scalar(
            select(BookingHold).where(BookingHold.payment_id == records["payment_id"])
        )
        persisted_appointment = db.get(Appointment, appointment.id)
        callbacks.append(
            payment.status == PaymentStatus.CAPTURED
            and hold.status == BookingHoldStatus.CONVERTED
            and persisted_appointment is not None
        )
        db.close()

    monkeypatch.setattr(
        "app.services.payment_verification.enqueue_confirmation_notification",
        assert_committed,
    )
    monkeypatch.setattr(
        "app.services.payment_verification.schedule_appointment_notifications",
        assert_committed,
    )

    response = _verify_request(records)

    assert response.status_code == 200
    assert callbacks == [True, True]
