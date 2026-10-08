import json
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.database import SessionLocal
from app.main import app
from app.models.appointment import Appointment, AppointmentStatus
from app.models.availability import ProviderAvailability
from app.models.booking_hold import BookingHold, BookingHoldStatus
from app.models.payment import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    PaymentWebhookEvent,
    PaymentWebhookEventStatus,
)
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.service import Service, ServiceStatus
from app.models.user import User, UserRole

client = TestClient(app)


@pytest.fixture
def webhook_records(monkeypatch):
    monkeypatch.setattr(
        "app.services.payment_verification.enqueue_confirmation_notification",
        lambda _appointment: None,
    )
    monkeypatch.setattr(
        "app.services.payment_verification.schedule_appointment_notifications",
        lambda _appointment: None,
    )

    db = SessionLocal()
    suffix = uuid4()
    customer = User(
        name=f"Webhook Customer {suffix}",
        email=f"webhook-customer-{suffix}@example.com",
        phone="+15550001002",
        password_hash="test",
        role=UserRole.CUSTOMER,
    )
    provider = Provider(
        name=f"Webhook Provider {suffix}",
        type=ProviderType.PERSON,
        email=f"webhook-provider-{suffix}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    service = Service(
        name=f"Webhook Service {suffix}",
        duration_minutes=30,
        category="Testing",
        capacity=1,
        buffer_time_minutes=10,
        price=Decimal("25.10"),
        status=ServiceStatus.ACTIVE,
    )
    db.add_all([customer, provider, service])
    db.flush()
    db.add(
        ProviderService(
            provider_id=provider.id,
            service_id=service.id,
            is_active=True,
        )
    )
    appointment_date = datetime.now(UTC).date() + timedelta(days=3)
    db.add(
        ProviderAvailability(
            provider_id=provider.id,
            day_of_week=appointment_date.weekday(),
            start_time=time(0, 0),
            end_time=time(23, 59),
            is_working_day=True,
        )
    )
    appointment_start = datetime.combine(appointment_date, time(10, 0), tzinfo=UTC)
    payment = Payment(
        customer_id=customer.id,
        amount=2510,
        currency="INR",
        status=PaymentStatus.CREATED,
        provider=PaymentProvider.RAZORPAY,
        provider_order_id=f"order_{uuid4().hex}",
    )
    db.add(payment)
    db.flush()
    hold = BookingHold(
        customer_id=customer.id,
        service_id=service.id,
        provider_id=provider.id,
        user_name="Webhook Recipient",
        user_email="webhook-recipient@example.com",
        user_phone="+15550003333",
        appointment_start=appointment_start,
        appointment_end=appointment_start + timedelta(minutes=30),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        notes="Webhook recipient notes",
        status=BookingHoldStatus.ACTIVE,
        payment_id=payment.id,
    )
    db.add(hold)
    db.commit()
    records = {
        "customer_id": customer.id,
        "customer_token": create_access_token(customer.id, UserRole.CUSTOMER),
        "provider_id": provider.id,
        "service_id": service.id,
        "payment_id": payment.id,
        "order_id": payment.provider_order_id,
        "provider_payment_id": f"pay_{uuid4().hex}",
        "event_id": f"evt_{uuid4().hex}",
        "signature": f"signature_{uuid4().hex}",
        "appointment_start": appointment_start,
        "recipient_name": "Webhook Recipient",
        "recipient_email": "webhook-recipient@example.com",
        "recipient_phone": "+15550003333",
        "recipient_notes": "Webhook recipient notes",
        "test_event_ids": [],
    }
    db.close()
    try:
        yield records
    finally:
        cleanup = SessionLocal()
        cleanup.execute(
            delete(PaymentWebhookEvent).where(
                PaymentWebhookEvent.provider_event_id.in_(records["test_event_ids"])
            )
        )
        cleanup.execute(
            delete(BookingHold).where(BookingHold.payment_id == records["payment_id"])
        )
        cleanup.execute(delete(Payment).where(Payment.id == records["payment_id"]))
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
        cleanup.execute(delete(User).where(User.id == records["customer_id"]))
        cleanup.commit()
        cleanup.close()


def _captured_payload(records, **entity_overrides):
    entity = {
        "id": records["provider_payment_id"],
        "order_id": records["order_id"],
        "amount": 2510,
        "currency": "INR",
        "status": "captured",
        "captured": True,
    }
    entity.update(entity_overrides)
    return {"event": "payment.captured", "payload": {"payment": {"entity": entity}}}


def _mock_signature(monkeypatch, valid=True):
    received = []

    class MockRazorpayService:
        def verify_webhook_signature(self, raw_body, signature):
            received.append((raw_body, signature))
            return valid

    monkeypatch.setattr("app.api.routes.payments.RazorpayService", MockRazorpayService)
    return received


def _post_webhook(records, monkeypatch, payload=None, *, event_id=None, signature=None):
    webhook_event_id = event_id or records["event_id"]
    if webhook_event_id not in records["test_event_ids"]:
        records["test_event_ids"].append(webhook_event_id)
    body = json.dumps(
        payload or _captured_payload(records), separators=(",", ":")
    ).encode()
    headers = {
        "X-Razorpay-Signature": signature or records["signature"],
        "X-Razorpay-Event-Id": webhook_event_id,
        "Content-Type": "application/json",
    }
    return client.post("/api/payments/webhook", content=body, headers=headers), body


def _state(records):
    db = SessionLocal()
    payment = db.get(Payment, records["payment_id"])
    hold = db.scalar(
        select(BookingHold).where(BookingHold.payment_id == records["payment_id"])
    )
    appointments = db.scalars(
        select(Appointment).where(Appointment.provider_id == records["provider_id"])
    ).all()
    events = db.scalars(
        select(PaymentWebhookEvent).where(
            PaymentWebhookEvent.provider_event_id.in_(records["test_event_ids"])
        )
    ).all()
    result = payment, hold, appointments, events
    db.close()
    return result


def test_valid_captured_webhook_creates_confirmed_appointment(
    webhook_records, monkeypatch
):
    records = webhook_records
    received = _mock_signature(monkeypatch)

    response, raw_body = _post_webhook(records, monkeypatch)

    assert response.status_code == 200
    assert response.json()["status"] == PaymentWebhookEventStatus.PROCESSED
    assert received == [(raw_body, records["signature"])]
    payment, hold, appointments, events = _state(records)
    assert len(appointments) == 1
    assert appointments[0].status == AppointmentStatus.CONFIRMED
    assert appointments[0].buffer_time_minutes == 10
    assert appointments[0].customer_id == records["customer_id"]
    assert appointments[0].user_name == records["recipient_name"]
    assert appointments[0].user_email == records["recipient_email"]
    assert appointments[0].user_phone == records["recipient_phone"]
    assert appointments[0].notes == records["recipient_notes"]
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.provider_payment_id == records["provider_payment_id"]
    assert payment.provider_signature is None
    assert payment.appointment_id == appointments[0].id
    assert hold.status == BookingHoldStatus.CONVERTED
    assert events[0].status == PaymentWebhookEventStatus.PROCESSED
    assert events[0].processed_at is not None


def test_invalid_signature_is_rejected_without_event(webhook_records, monkeypatch):
    records = webhook_records
    _mock_signature(monkeypatch, valid=False)

    response, _ = _post_webhook(records, monkeypatch)

    assert response.status_code == 400
    assert _state(records)[3] == []


def test_missing_signature_is_rejected(webhook_records, monkeypatch):
    records = webhook_records
    received = _mock_signature(monkeypatch)
    body = json.dumps(_captured_payload(records)).encode()

    response = client.post(
        "/api/payments/webhook",
        content=body,
        headers={"X-Razorpay-Event-Id": records["event_id"]},
    )

    assert response.status_code == 400
    assert received == []
    assert _state(records)[3] == []


def test_unknown_event_is_durably_ignored(webhook_records, monkeypatch):
    records = webhook_records
    _mock_signature(monkeypatch)
    response, _ = _post_webhook(
        records,
        monkeypatch,
        {"event": "payment.failed", "payload": {}},
    )

    assert response.status_code == 200
    assert response.json()["status"] == PaymentWebhookEventStatus.IGNORED
    payment, hold, appointments, events = _state(records)
    assert payment.status == PaymentStatus.CREATED
    assert hold.status == BookingHoldStatus.ACTIVE
    assert appointments == []
    assert events[0].status == PaymentWebhookEventStatus.IGNORED


def test_unknown_order_is_recorded_without_payment_or_appointment(
    webhook_records, monkeypatch
):
    records = webhook_records
    _mock_signature(monkeypatch)
    response, _ = _post_webhook(
        records,
        monkeypatch,
        _captured_payload(records, order_id=f"order_{uuid4().hex}"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == PaymentWebhookEventStatus.IGNORED
    payment, hold, appointments, events = _state(records)
    assert payment.status == PaymentStatus.CREATED
    assert hold.status == BookingHoldStatus.ACTIVE
    assert appointments == []
    assert events[0].provider_order_id.startswith("order_")


def test_duplicate_event_id_does_not_repeat_work(webhook_records, monkeypatch):
    records = webhook_records
    _mock_signature(monkeypatch)
    notifications = []
    monkeypatch.setattr(
        "app.services.payment_verification.enqueue_confirmation_notification",
        lambda appointment: notifications.append(("confirmation", appointment.id)),
    )
    monkeypatch.setattr(
        "app.services.payment_verification.schedule_appointment_notifications",
        lambda appointment: notifications.append(("reminders", appointment.id)),
    )
    first, _ = _post_webhook(records, monkeypatch)
    before = _state(records)
    second, _ = _post_webhook(records, monkeypatch)
    after = _state(records)

    assert first.status_code == second.status_code == 200
    assert len(after[2]) == len(before[2]) == 1
    assert len(after[3]) == len(before[3]) == 1
    assert after[0].appointment_id == before[0].appointment_id
    assert [kind for kind, _ in notifications] == ["confirmation", "reminders"]


def test_same_payment_under_new_event_id_does_not_duplicate_appointment(
    webhook_records, monkeypatch
):
    records = webhook_records
    _mock_signature(monkeypatch)
    _post_webhook(records, monkeypatch)
    response, _ = _post_webhook(records, monkeypatch, event_id=f"evt_{uuid4().hex}")

    assert response.status_code == 200
    payment, hold, appointments, events = _state(records)
    assert len(appointments) == 1
    assert len(events) == 2
    assert payment.appointment_id == appointments[0].id
    assert hold.status == BookingHoldStatus.CONVERTED


def test_linked_payment_with_matching_amount_and_currency_is_processed(
    webhook_records, monkeypatch
):
    records = webhook_records
    _mock_signature(monkeypatch)
    first, _ = _post_webhook(records, monkeypatch)
    second, _ = _post_webhook(records, monkeypatch, event_id=f"evt_{uuid4().hex}")

    payment, hold, appointments, events = _state(records)
    assert first.status_code == second.status_code == 200
    assert second.json()["status"] == PaymentWebhookEventStatus.PROCESSED
    assert payment.status == PaymentStatus.CAPTURED
    assert hold.status == BookingHoldStatus.CONVERTED
    assert len(appointments) == 1
    assert len(events) == 2


@pytest.mark.parametrize(
    ("overrides", "error_fragment"),
    [
        ({"amount": 1}, "amount or currency"),
        ({"currency": "USD"}, "amount or currency"),
    ],
)
def test_linked_payment_mismatches_are_reconciliation_failures(
    webhook_records, monkeypatch, overrides, error_fragment
):
    records = webhook_records
    _mock_signature(monkeypatch)
    first, _ = _post_webhook(records, monkeypatch)
    second, _ = _post_webhook(
        records,
        monkeypatch,
        _captured_payload(records, **overrides),
        event_id=f"evt_{uuid4().hex}",
    )

    payment, hold, appointments, events = _state(records)
    mismatch_event = next(event for event in events if event.status != "PROCESSED")
    assert first.status_code == second.status_code == 200
    assert second.json()["status"] == PaymentWebhookEventStatus.FAILED
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.appointment_id == appointments[0].id
    assert hold.status == BookingHoldStatus.CONVERTED
    assert len(appointments) == 1
    assert error_fragment in mismatch_event.error_message


def test_failed_local_payment_preserves_valid_external_capture(
    webhook_records, monkeypatch
):
    records = webhook_records
    db = SessionLocal()
    payment = db.get(Payment, records["payment_id"])
    payment.status = PaymentStatus.FAILED
    hold = db.scalar(
        select(BookingHold).where(BookingHold.payment_id == records["payment_id"])
    )
    hold.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    db.close()
    _mock_signature(monkeypatch)

    response, _ = _post_webhook(records, monkeypatch)

    payment, hold, appointments, events = _state(records)
    assert response.status_code == 200
    assert response.json()["status"] == PaymentWebhookEventStatus.FAILED
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.provider_payment_id == records["provider_payment_id"]
    assert payment.appointment_id is None
    assert hold.status == BookingHoldStatus.ACTIVE
    assert appointments == []
    assert events[0].status == PaymentWebhookEventStatus.FAILED


def test_webhook_after_browser_verification_does_not_change_appointment(
    webhook_records, monkeypatch
):
    records = webhook_records
    _mock_signature(monkeypatch)
    notifications = []
    monkeypatch.setattr(
        "app.services.payment_verification.enqueue_confirmation_notification",
        lambda appointment: notifications.append(("confirmation", appointment.id)),
    )
    monkeypatch.setattr(
        "app.services.payment_verification.schedule_appointment_notifications",
        lambda appointment: notifications.append(("reminders", appointment.id)),
    )

    class MockBrowserRazorpayService:
        def verify_payment(self, *_args):
            return True

    monkeypatch.setattr(
        "app.services.payment_verification.RazorpayService",
        MockBrowserRazorpayService,
    )
    browser_response = client.post(
        "/api/payments/verify",
        headers={
            "Authorization": f"Bearer {create_access_token(records['customer_id'], UserRole.CUSTOMER)}"
        },
        json={
            "payment_id": records["provider_payment_id"],
            "order_id": records["order_id"],
            "signature": records["signature"],
        },
    )
    before = _state(records)[2][0]
    before_values = (
        before.status,
        before.appointment_start,
        before.appointment_end,
        before.buffer_time_minutes,
    )
    response, _ = _post_webhook(records, monkeypatch)

    assert browser_response.status_code == 200
    assert response.status_code == 200
    payment, hold, appointments, events = _state(records)
    assert len(appointments) == 1
    assert (
        appointments[0].status,
        appointments[0].appointment_start,
        appointments[0].appointment_end,
        appointments[0].buffer_time_minutes,
    ) == before_values
    assert payment.appointment_id == appointments[0].id
    assert hold.status == BookingHoldStatus.CONVERTED
    assert events[0].status == PaymentWebhookEventStatus.PROCESSED
    assert [kind for kind, _ in notifications] == ["confirmation", "reminders"]


def test_webhook_before_browser_verification_is_idempotent(
    webhook_records, monkeypatch
):
    records = webhook_records
    _mock_signature(monkeypatch)
    response, _ = _post_webhook(records, monkeypatch)

    class BrowserMustNotReverify:
        def verify_payment(self, *_args):
            raise AssertionError("captured webhook payment should be idempotent")

    monkeypatch.setattr(
        "app.services.payment_verification.RazorpayService", BrowserMustNotReverify
    )
    browser_response = client.post(
        "/api/payments/verify",
        headers={
            "Authorization": f"Bearer {create_access_token(records['customer_id'], UserRole.CUSTOMER)}"
        },
        json={
            "payment_id": records["provider_payment_id"],
            "order_id": records["order_id"],
            "signature": records["signature"],
        },
    )

    assert response.status_code == browser_response.status_code == 200
    assert len(_state(records)[2]) == 1


def test_webhook_before_browser_uses_hold_recipient_snapshot(
    webhook_records, monkeypatch
):
    records = webhook_records
    _mock_signature(monkeypatch)
    response, _ = _post_webhook(records, monkeypatch)

    assert response.status_code == 200
    appointment = _state(records)[2][0]
    assert appointment.customer_id == records["customer_id"]
    assert appointment.user_name == records["recipient_name"]
    assert appointment.user_email == records["recipient_email"]
    assert appointment.user_phone == records["recipient_phone"]
    assert appointment.notes == records["recipient_notes"]


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"amount": 1}, "amount or currency"),
        ({"currency": "USD"}, "amount or currency"),
        ({"id": f"pay_{uuid4().hex}"}, "payment ID conflicts"),
    ],
)
def test_captured_payment_mismatches_are_recorded_for_reconciliation(
    webhook_records, monkeypatch, overrides, reason
):
    records = webhook_records
    if "id" in overrides:
        db = SessionLocal()
        db.get(Payment, records["payment_id"]).provider_payment_id = "pay_previous"
        db.commit()
        db.close()
    _mock_signature(monkeypatch)

    response, _ = _post_webhook(
        records, monkeypatch, _captured_payload(records, **overrides)
    )

    assert response.status_code == 200
    payment, hold, appointments, events = _state(records)
    assert payment.status == PaymentStatus.CAPTURED
    assert hold.status == BookingHoldStatus.ACTIVE
    assert appointments == []
    assert events[0].status == PaymentWebhookEventStatus.FAILED
    assert reason in events[0].error_message


def test_expired_hold_records_captured_payment_without_appointment(
    webhook_records, monkeypatch
):
    records = webhook_records
    db = SessionLocal()
    hold = db.scalar(
        select(BookingHold).where(BookingHold.payment_id == records["payment_id"])
    )
    hold.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    db.close()
    _mock_signature(monkeypatch)

    response, _ = _post_webhook(records, monkeypatch)

    assert response.status_code == 200
    payment, hold, appointments, events = _state(records)
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.provider_payment_id == records["provider_payment_id"]
    assert hold.status == BookingHoldStatus.EXPIRED
    assert appointments == []
    assert events[0].status == PaymentWebhookEventStatus.FAILED


def test_unavailable_slot_is_recorded_for_reconciliation(webhook_records, monkeypatch):
    records = webhook_records
    existing = Appointment(
        service_id=records["service_id"],
        provider_id=records["provider_id"],
        user_name="Existing booking",
        user_email="existing-webhook@example.com",
        appointment_start=records["appointment_start"],
        appointment_end=records["appointment_start"] + timedelta(minutes=30),
        duration_minutes=30,
        buffer_time_minutes=10,
        status=AppointmentStatus.CONFIRMED,
    )
    db = SessionLocal()
    db.add(existing)
    db.commit()
    existing_id = existing.id
    db.close()
    _mock_signature(monkeypatch)

    response, _ = _post_webhook(records, monkeypatch)

    assert response.status_code == 200
    payment, hold, appointments, events = _state(records)
    assert payment.status == PaymentStatus.CAPTURED
    assert hold.status == BookingHoldStatus.ACTIVE
    assert len(appointments) == 1
    assert appointments[0].id == existing_id
    assert events[0].status == PaymentWebhookEventStatus.FAILED


def test_notifications_are_queued_only_after_commit(webhook_records, monkeypatch):
    records = webhook_records
    _mock_signature(monkeypatch)
    callbacks = []

    def check_committed(appointment):
        db = SessionLocal()
        payment = db.get(Payment, records["payment_id"])
        hold = db.scalar(
            select(BookingHold).where(BookingHold.payment_id == records["payment_id"])
        )
        stored_appointment = db.get(Appointment, appointment.id)
        callbacks.append(
            payment.status == PaymentStatus.CAPTURED
            and hold.status == BookingHoldStatus.CONVERTED
            and stored_appointment is not None
        )
        db.close()

    monkeypatch.setattr(
        "app.services.payment_verification.enqueue_confirmation_notification",
        check_committed,
    )
    monkeypatch.setattr(
        "app.services.payment_verification.schedule_appointment_notifications",
        check_committed,
    )

    response, _ = _post_webhook(records, monkeypatch)

    assert response.status_code == 200
    assert callbacks == [True, True]


def test_database_failure_returns_retryable_response_and_rolls_back(
    webhook_records, monkeypatch
):
    records = webhook_records
    _mock_signature(monkeypatch)
    original_commit = Session.commit

    def fail_commit(session):
        raise OperationalError("commit", {}, RuntimeError("database unavailable"))

    monkeypatch.setattr(Session, "commit", fail_commit)
    response, _ = _post_webhook(records, monkeypatch)
    monkeypatch.setattr(Session, "commit", original_commit)

    assert response.status_code == 503
    payment, hold, appointments, events = _state(records)
    assert payment.status == PaymentStatus.CREATED
    assert hold.status == BookingHoldStatus.ACTIVE
    assert appointments == []
    assert events == []


def test_webhook_requires_no_customer_authentication(webhook_records, monkeypatch):
    records = webhook_records
    _mock_signature(monkeypatch)

    response, _ = _post_webhook(records, monkeypatch)

    assert response.status_code == 200
    assert len(_state(records)[2]) == 1
