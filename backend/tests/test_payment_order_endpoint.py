from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from threading import Barrier
from time import sleep
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.security import create_access_token
from app.db.database import SessionLocal
from app.main import app
from app.models.appointment import Appointment
from app.models.availability import ProviderAvailability
from app.models.booking_hold import BookingHold, BookingHoldStatus
from app.models.payment import Payment, PaymentProvider, PaymentStatus
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.service import Service, ServiceStatus
from app.models.user import User, UserRole
from app.schemas.payment import AppointmentPaymentOrderCreate
from app.services.booking import BookingConflictError
from app.services.payment_orders import (
    PAYMENT_CURRENCY,
    create_appointment_payment_order,
)
from app.services.razorpay import RazorpayIntegrationError

client = TestClient(app)


@pytest.fixture
def payment_order_records(monkeypatch):
    db = SessionLocal()
    suffix = uuid4()
    customer = User(
        name=f"Payment Customer {suffix}",
        email=f"payment-customer-{suffix}@example.com",
        password_hash="test",
        role=UserRole.CUSTOMER,
    )
    provider_user = User(
        name=f"Payment Provider User {suffix}",
        email=f"payment-provider-user-{suffix}@example.com",
        password_hash="test",
        role=UserRole.PROVIDER,
    )
    other_customer = User(
        name=f"Other Payment Customer {suffix}",
        email=f"other-payment-customer-{suffix}@example.com",
        password_hash="test",
        role=UserRole.CUSTOMER,
    )
    provider = Provider(
        name=f"Payment Provider {suffix}",
        type=ProviderType.PERSON,
        email=f"payment-provider-{suffix}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    service = Service(
        name=f"Payment Service {suffix}",
        duration_minutes=30,
        category="Testing",
        capacity=1,
        buffer_time_minutes=10,
        price=Decimal("25.10"),
        status=ServiceStatus.ACTIVE,
    )
    db.add_all([customer, provider_user, other_customer, provider, service])
    db.flush()
    provider_service = ProviderService(
        provider_id=provider.id,
        service_id=service.id,
        is_active=True,
    )
    db.add(provider_service)

    target_day = datetime.now(UTC).date() + timedelta(days=2)
    db.add(
        ProviderAvailability(
            provider_id=provider.id,
            day_of_week=target_day.weekday(),
            start_time=time(0, 0),
            end_time=time(23, 59),
            is_working_day=True,
        )
    )
    db.commit()

    start = datetime.combine(target_day, time(10, 0), tzinfo=ZoneInfo("UTC"))
    records = {
        "customer_id": customer.id,
        "customer_token": create_access_token(customer.id, customer.role),
        "customer_name": customer.name,
        "customer_email": customer.email,
        "customer_phone": customer.phone,
        "other_customer_id": other_customer.id,
        "other_customer_token": create_access_token(
            other_customer.id, other_customer.role
        ),
        "provider_user_id": provider_user.id,
        "provider_token": create_access_token(provider_user.id, provider_user.role),
        "provider_id": provider.id,
        "service_id": service.id,
        "appointment_start": start,
    }
    db.close()

    monkeypatch.setattr(settings, "razorpay_key_id", "test_public_key")
    try:
        yield records
    finally:
        cleanup = SessionLocal()
        cleanup.execute(
            delete(BookingHold).where(BookingHold.provider_id == records["provider_id"])
        )
        cleanup.execute(
            delete(Payment).where(
                Payment.customer_id.in_(
                    [records["customer_id"], records["other_customer_id"]]
                )
            )
        )
        cleanup.execute(
            delete(Appointment).where(Appointment.provider_id == records["provider_id"])
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
        cleanup.execute(
            delete(User).where(
                User.id.in_(
                    [
                        records["customer_id"],
                        records["other_customer_id"],
                        records["provider_user_id"],
                    ]
                )
            )
        )
        cleanup.commit()
        cleanup.close()


def _request_order(records, *, token=None, body=None):
    return client.post(
        "/api/payments/order",
        headers={"Authorization": f"Bearer {token or records['customer_token']}"},
        json=body
        or {
            "service_id": str(records["service_id"]),
            "provider_id": str(records["provider_id"]),
            "appointment_start": records["appointment_start"].isoformat(),
            "user_name": "Appointment Recipient",
            "user_email": "appointment-recipient@example.com",
            "user_phone": "+15550001111",
            "notes": "Recipient booking notes",
        },
    )


def _mock_razorpay_order(monkeypatch, *, result=None, error=None):
    calls = []

    class MockRazorpayService:
        def create_order(self, **kwargs):
            calls.append(kwargs)
            if error is not None:
                raise error
            return result or {"id": f"order_{uuid4().hex}"}

    monkeypatch.setattr(
        "app.services.payment_orders.RazorpayService", MockRazorpayService
    )
    return calls


def test_creates_payment_order_and_active_hold(payment_order_records, monkeypatch):
    records = payment_order_records
    calls = _mock_razorpay_order(monkeypatch)

    response = _request_order(records)

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["key_id"] == "test_public_key"
    assert data["amount"] == 2510
    assert data["currency"] == PAYMENT_CURRENCY == "INR"
    assert data["order_id"].startswith("order_")
    assert calls == [
        {
            "amount": 2510,
            "currency": "INR",
            "receipt": data["payment_id"],
        }
    ]

    db = SessionLocal()
    payment = db.get(Payment, data["payment_id"])
    hold = db.scalar(
        select(BookingHold).where(BookingHold.payment_id == data["payment_id"])
    )
    appointment_count = db.scalar(
        select(func.count())
        .select_from(Appointment)
        .where(Appointment.provider_id == records["provider_id"])
    )
    assert payment is not None
    assert payment.customer_id == records["customer_id"]
    assert payment.amount == 2510
    assert payment.status == PaymentStatus.CREATED
    assert payment.provider == PaymentProvider.RAZORPAY
    assert payment.appointment_id is None
    assert payment.series_id is None
    assert payment.provider_order_id == data["order_id"]
    assert hold is not None
    assert hold.status == BookingHoldStatus.ACTIVE
    assert hold.customer_id == records["customer_id"]
    assert hold.user_name == "Appointment Recipient"
    assert hold.user_email == "appointment-recipient@example.com"
    assert hold.user_phone == "+15550001111"
    assert hold.notes == "Recipient booking notes"
    assert hold.appointment_start == records["appointment_start"]
    assert hold.appointment_end == records["appointment_start"] + timedelta(minutes=30)
    assert hold.expires_at > datetime.now(UTC)
    assert hold.expires_at <= datetime.now(UTC) + timedelta(minutes=11)
    assert appointment_count == 0
    db.close()


def test_payment_order_rejects_client_customer_id(payment_order_records, monkeypatch):
    records = payment_order_records
    calls = _mock_razorpay_order(monkeypatch)

    response = _request_order(
        records,
        body={
            "service_id": str(records["service_id"]),
            "provider_id": str(records["provider_id"]),
            "appointment_start": records["appointment_start"].isoformat(),
            "user_name": "Appointment Recipient",
            "user_email": "appointment-recipient@example.com",
            "customer_id": str(records["other_customer_id"]),
        },
    )

    assert response.status_code == 422
    assert calls == []


def test_payment_order_can_snapshot_authenticated_customer_as_recipient(
    payment_order_records, monkeypatch
):
    records = payment_order_records
    _mock_razorpay_order(monkeypatch)

    response = _request_order(
        records,
        body={
            "service_id": str(records["service_id"]),
            "provider_id": str(records["provider_id"]),
            "appointment_start": records["appointment_start"].isoformat(),
            "user_name": records["customer_name"],
            "user_email": records["customer_email"],
            "user_phone": records["customer_phone"],
            "notes": None,
        },
    )

    assert response.status_code == 201
    db = SessionLocal()
    payment = db.get(Payment, response.json()["payment_id"])
    hold = db.scalar(
        select(BookingHold).where(
            BookingHold.payment_id == response.json()["payment_id"]
        )
    )
    assert payment.customer_id == records["customer_id"]
    assert hold.customer_id == records["customer_id"]
    assert hold.user_name == records["customer_name"]
    assert hold.user_email == records["customer_email"]
    assert hold.user_phone == records["customer_phone"]
    assert hold.notes is None
    db.close()


def test_razorpay_failure_rolls_back_payment_and_hold(
    payment_order_records, monkeypatch
):
    records = payment_order_records
    _mock_razorpay_order(
        monkeypatch, error=RazorpayIntegrationError("sanitized failure")
    )

    response = _request_order(records)

    assert response.status_code == 502
    assert response.json() == {"detail": "Unable to create payment order"}
    db = SessionLocal()
    assert (
        db.scalar(
            select(func.count())
            .select_from(Payment)
            .where(Payment.customer_id == records["customer_id"])
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(BookingHold)
            .where(BookingHold.provider_id == records["provider_id"])
        )
        == 0
    )
    db.close()


def test_active_hold_makes_slot_unavailable(payment_order_records, monkeypatch):
    records = payment_order_records
    db = SessionLocal()
    existing_hold = BookingHold(
        customer_id=records["customer_id"],
        service_id=records["service_id"],
        provider_id=records["provider_id"],
        user_name="Existing Hold Recipient",
        user_email="existing-hold@example.com",
        appointment_start=records["appointment_start"],
        appointment_end=records["appointment_start"] + timedelta(minutes=30),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        status=BookingHoldStatus.ACTIVE,
    )
    db.add(existing_hold)
    db.commit()
    db.close()
    calls = _mock_razorpay_order(monkeypatch)

    response = _request_order(records)

    assert response.status_code == 409
    assert response.json()["detail"] == "Appointment slot is already held"
    assert calls == []


def test_concurrent_order_requests_create_only_one_hold(
    payment_order_records, monkeypatch
):
    records = payment_order_records

    class SlowMockRazorpayService:
        def create_order(self, **kwargs):
            sleep(0.2)
            return {"id": f"order_{uuid4().hex}"}

    monkeypatch.setattr(
        "app.services.payment_orders.RazorpayService", SlowMockRazorpayService
    )
    barrier = Barrier(2)
    outcomes = []

    def create_order(customer_id):
        db = SessionLocal()
        try:
            customer = db.get(User, customer_id)
            payload = AppointmentPaymentOrderCreate(
                service_id=records["service_id"],
                provider_id=records["provider_id"],
                appointment_start=records["appointment_start"],
                user_name="Concurrent Recipient",
                user_email="concurrent-recipient@example.com",
            )
            barrier.wait(timeout=5)
            payment = create_appointment_payment_order(db, customer, payload)
            outcomes.append(("created", payment.id))
        except BookingConflictError:
            outcomes.append(("conflict", None))
        finally:
            db.rollback()
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(create_order, records["customer_id"]),
            executor.submit(create_order, records["other_customer_id"]),
        ]
        for future in futures:
            future.result(timeout=10)

    assert sorted(outcome[0] for outcome in outcomes) == ["conflict", "created"]
    db = SessionLocal()
    assert (
        db.scalar(
            select(func.count())
            .select_from(BookingHold)
            .where(BookingHold.provider_id == records["provider_id"])
        )
        == 1
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(Payment)
            .where(
                Payment.customer_id.in_(
                    [records["customer_id"], records["other_customer_id"]]
                )
            )
        )
        == 1
    )
    db.close()


def test_provider_cannot_create_customer_payment_order(
    payment_order_records, monkeypatch
):
    records = payment_order_records
    calls = _mock_razorpay_order(monkeypatch)

    response = _request_order(records, token=records["provider_token"])

    assert response.status_code == 403
    assert calls == []


def test_customer_id_is_derived_from_authenticated_user(
    payment_order_records, monkeypatch
):
    records = payment_order_records
    calls = _mock_razorpay_order(monkeypatch)
    body = {
        "service_id": str(records["service_id"]),
        "provider_id": str(records["provider_id"]),
        "appointment_start": records["appointment_start"].isoformat(),
        "customer_id": str(records["provider_user_id"]),
    }

    response = _request_order(records, body=body)

    assert response.status_code == 422
    assert calls == []
