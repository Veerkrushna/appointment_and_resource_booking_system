from datetime import UTC, datetime, time, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from razorpay.errors import SignatureVerificationError

from app.db.database import SessionLocal
from app.main import app
from app.models.appointment import Appointment, AppointmentStatus
from app.models.availability import ProviderAvailability
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.service import Service, ServiceStatus
from app.models.user import User, UserRole
from app.payments.models import Payment, PaymentStatus
from app.schemas.appointment import AppointmentCreate
from app.services.booking import BookingConflictError, create_appointment

client = TestClient(app)


@pytest.fixture
def test_setup():
    db = SessionLocal()

    # Create dummy provider and service
    provider = Provider(
        name="Payment Test Provider",
        type=ProviderType.PERSON,
        email=f"payment-provider-{uuid4()}@example.com",
        availability_status=AvailabilityStatus.AVAILABLE,
        timezone="UTC",
    )
    db.add(provider)
    db.flush()

    service = Service(
        name="Payment Test Service",
        category="General",
        duration_minutes=30,
        price=150.00,  # 150 INR -> 15000 paise
        status=ServiceStatus.ACTIVE,
    )
    db.add(service)
    db.flush()

    # Link provider and service
    ps = ProviderService(
        provider_id=provider.id,
        service_id=service.id,
        is_active=True,
    )
    db.add(ps)

    # Create customer
    user = User(
        name="Pay Test Customer",
        email=f"pay-test-{uuid4()}@example.com",
        password_hash="test-hash",
        role=UserRole.CUSTOMER,
    )
    db.add(user)
    db.flush()

    # Create pending appointment
    now_utc = datetime.now(UTC)
    appointment = Appointment(
        service_id=service.id,
        provider_id=provider.id,
        customer_id=user.id,
        user_name="Pay Test Customer",
        user_email=user.email,
        appointment_start=now_utc + timedelta(days=2),
        appointment_end=now_utc + timedelta(days=2, minutes=30),
        duration_minutes=30,
        status=AppointmentStatus.PENDING,
    )
    db.add(appointment)

    # Provider availability
    avail = ProviderAvailability(
        provider_id=provider.id,
        day_of_week=appointment.appointment_start.weekday(),
        start_time=time(0, 0),
        end_time=time(23, 59),
    )
    db.add(avail)

    db.commit()
    db.refresh(appointment)
    provider_id = provider.id
    service_id = service.id
    user_id = user.id
    appointment_id = appointment.id
    db.close()

    yield {
        "provider_id": provider_id,
        "service_id": service_id,
        "user_id": user_id,
        "appointment_id": appointment_id,
    }

    # Teardown
    db = SessionLocal()
    db.query(Payment).filter_by(booking_id=appointment_id).delete()
    db.query(Appointment).filter(
        (Appointment.id == appointment_id)
        | (Appointment.provider_id == provider_id)
    ).delete()
    db.query(ProviderAvailability).filter_by(provider_id=provider_id).delete()
    db.query(ProviderService).filter_by(provider_id=provider_id).delete()
    db.query(User).filter_by(id=user_id).delete()
    db.query(Service).filter_by(id=service_id).delete()
    db.query(Provider).filter_by(id=provider_id).delete()
    db.commit()
    db.close()


def test_create_order_missing_booking():
    response = client.post(
        "/payments/create-order",
        json={"booking_id": str(uuid4())},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Booking not found"


def test_create_order_non_pending_booking(test_setup):
    db = SessionLocal()
    appointment = db.get(Appointment, test_setup["appointment_id"])
    appointment.status = AppointmentStatus.CONFIRMED
    db.commit()
    db.close()

    response = client.post(
        "/payments/create-order",
        json={"booking_id": str(test_setup["appointment_id"])},
    )
    assert response.status_code == 409
    assert "not in PENDING state" in response.json()["detail"]

    # Revert for other tests
    db = SessionLocal()
    appointment = db.get(Appointment, test_setup["appointment_id"])
    appointment.status = AppointmentStatus.PENDING
    db.commit()
    db.close()


def test_create_order_success(test_setup):
    mock_order = {"id": "order_test_123456", "amount": 15000, "currency": "INR"}

    with patch("app.payments.router.get_razorpay_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.order.create.return_value = mock_order
        mock_get_client.return_value = mock_client

        response = client.post(
            "/payments/create-order",
            json={"booking_id": str(test_setup["appointment_id"])},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == "order_test_123456"
        assert data["amount"] == 15000
        assert data["currency"] == "INR"
        assert "key_id" in data

        # Check Payment row in database
        db = SessionLocal()
        payment = db.query(Payment).filter_by(provider_order_id="order_test_123456").first()
        assert payment is not None
        assert payment.booking_id == test_setup["appointment_id"]
        assert payment.status == PaymentStatus.CREATED
        assert payment.amount_paise == 15000
        db.delete(payment)
        db.commit()
        db.close()


def test_verify_payment_valid_signature(test_setup):
    db = SessionLocal()
    payment = Payment(
        booking_id=test_setup["appointment_id"],
        provider="razorpay",
        provider_order_id="order_valid_sig_123",
        amount_paise=15000,
        currency="INR",
        status=PaymentStatus.CREATED,
    )
    db.add(payment)
    db.commit()
    db.close()

    with patch("app.payments.router.get_razorpay_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.return_value = True
        mock_get_client.return_value = mock_client

        response = client.post(
            "/payments/verify",
            json={
                "razorpay_order_id": "order_valid_sig_123",
                "razorpay_payment_id": "pay_test_999",
                "razorpay_signature": "valid_signature_dummy",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # Check Payment and Appointment status
        db = SessionLocal()
        db_payment = db.query(Payment).filter_by(provider_order_id="order_valid_sig_123").first()
        assert db_payment.status == PaymentStatus.PAID
        assert db_payment.provider_payment_id == "pay_test_999"

        db_appointment = db.get(Appointment, test_setup["appointment_id"])
        assert db_appointment.status == AppointmentStatus.CONFIRMED
        assert db_appointment.confirmed_at is not None

        # Verify idempotency
        second_response = client.post(
            "/payments/verify",
            json={
                "razorpay_order_id": "order_valid_sig_123",
                "razorpay_payment_id": "pay_test_999",
                "razorpay_signature": "valid_signature_dummy",
            },
        )
        assert second_response.status_code == 200

        db.delete(db_payment)
        db.commit()
        db.close()


def test_verify_payment_invalid_signature(test_setup):
    db = SessionLocal()
    payment = Payment(
        booking_id=test_setup["appointment_id"],
        provider="razorpay",
        provider_order_id="order_invalid_sig_456",
        amount_paise=15000,
        currency="INR",
        status=PaymentStatus.CREATED,
    )
    db.add(payment)
    db.commit()
    db.close()

    with patch("app.payments.router.get_razorpay_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.side_effect = SignatureVerificationError("bad sig")
        mock_get_client.return_value = mock_client

        response = client.post(
            "/payments/verify",
            json={
                "razorpay_order_id": "order_invalid_sig_456",
                "razorpay_payment_id": "pay_fail_000",
                "razorpay_signature": "invalid_sig",
            },
        )
        assert response.status_code == 400
        assert "invalid signature" in response.json()["detail"]

        # Check Payment status became FAILED and booking remained PENDING (or unconfirmed)
        db = SessionLocal()
        db_payment = db.query(Payment).filter_by(provider_order_id="order_invalid_sig_456").first()
        assert db_payment.status == PaymentStatus.FAILED

        db_appointment = db.get(Appointment, test_setup["appointment_id"])
        assert db_appointment.status != AppointmentStatus.CONFIRMED

        db.delete(db_payment)
        db.commit()
        db.close()


def test_webhook_payment_captured(test_setup):
    db = SessionLocal()
    payment = Payment(
        booking_id=test_setup["appointment_id"],
        provider="razorpay",
        provider_order_id="order_webhook_789",
        amount_paise=15000,
        currency="INR",
        status=PaymentStatus.CREATED,
    )
    db.add(payment)
    db.commit()
    db.close()

    webhook_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_hook_111",
                    "order_id": "order_webhook_789",
                    "amount": 15000,
                    "status": "captured",
                }
            }
        },
    }

    import json

    with patch("app.payments.router.get_razorpay_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.utility.verify_webhook_signature.return_value = True
        mock_get_client.return_value = mock_client

        response = client.post(
            "/payments/webhook",
            content=json.dumps(webhook_payload),
            headers={"X-Razorpay-Signature": "dummy_webhook_sig", "Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        db = SessionLocal()
        db_payment = db.query(Payment).filter_by(provider_order_id="order_webhook_789").first()
        assert db_payment.status == PaymentStatus.PAID

        db_appointment = db.get(Appointment, test_setup["appointment_id"])
        assert db_appointment.status == AppointmentStatus.CONFIRMED

        db.delete(db_payment)
        db.commit()
        db.close()


def test_create_order_expired_pending(test_setup):
    db = SessionLocal()
    appointment = db.get(Appointment, test_setup["appointment_id"])
    appointment.created_at = datetime.now(UTC) - timedelta(minutes=15)
    db.commit()
    db.close()

    response = client.post(
        "/payments/create-order",
        json={"booking_id": str(test_setup["appointment_id"])},
    )
    assert response.status_code == 409
    assert "expired" in response.json()["detail"].lower()

    # Revert created_at
    db = SessionLocal()
    appointment = db.get(Appointment, test_setup["appointment_id"])
    appointment.created_at = datetime.now(UTC)
    appointment.status = AppointmentStatus.PENDING
    db.commit()
    db.close()


def test_slot_protection_pending_holds_slot(test_setup):
    db = SessionLocal()
    appointment = db.get(Appointment, test_setup["appointment_id"])
    payload = AppointmentCreate(
        service_id=test_setup["service_id"],
        provider_id=test_setup["provider_id"],
        user_name="Other User",
        user_email="other@example.com",
        appointment_start=appointment.appointment_start,
    )

    with pytest.raises(BookingConflictError):
        create_appointment(db, payload)

    db.close()


def test_slot_protection_expired_releases_slot(test_setup):
    db = SessionLocal()
    appointment = db.get(Appointment, test_setup["appointment_id"])
    # Expire previous appointment
    appointment.created_at = datetime.now(UTC) - timedelta(minutes=15)
    appointment_start = appointment.appointment_start
    db.commit()

    payload = AppointmentCreate(
        service_id=test_setup["service_id"],
        provider_id=test_setup["provider_id"],
        user_name="Second User",
        user_email="second@example.com",
        appointment_start=appointment_start,
    )
    new_appt = create_appointment(db, payload)
    assert new_appt is not None
    assert new_appt.id != test_setup["appointment_id"]

    db.delete(new_appt)
    db.commit()
    db.close()


def test_pay_at_appointment_success(test_setup):
    response = client.post(
        "/payments/pay-at-appointment",
        json={"booking_id": str(test_setup["appointment_id"])},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    db = SessionLocal()
    appointment = db.get(Appointment, test_setup["appointment_id"])
    assert appointment.status == AppointmentStatus.CONFIRMED
    assert appointment.confirmed_at is not None
    db.close()
