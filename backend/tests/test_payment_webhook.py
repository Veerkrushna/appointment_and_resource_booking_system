import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from threading import Barrier
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
from app.models.appointment_series import (
    AppointmentSeries,
    AppointmentSeriesEndMode,
    AppointmentSeriesFrequency,
    AppointmentSeriesStatus,
)
from app.models.availability import ProviderAvailability
from app.models.booking_hold import BookingHold, BookingHoldStatus
from app.models.payment import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    PaymentWebhookCaptureValidationFailure,
    PaymentWebhookEvent,
    PaymentWebhookEventStatus,
)
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.service import Service, ServiceStatus
from app.models.user import User, UserRole
from app.schemas.payment_reconciliation import PaymentReconciliationReason
from app.services.payment_reconciliation import (
    list_payment_reconciliation_candidates,
)
from app.services.payment_webhooks import _capture_observation_value

client = TestClient(app)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (True, True),
        (False, False),
        (0, 0),
        (2**53 - 1, 2**53 - 1),
        (-(2**53 - 1), -(2**53 - 1)),
        (1.25, 1.25),
        (0.0, 0.0),
        ("x" * 256, "x" * 255),
    ],
)
def test_capture_observation_value_preserves_bounded_values(value, expected):
    assert _capture_observation_value(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        math.nan,
        math.inf,
        -math.inf,
        2**53,
        -(2**53),
    ],
)
def test_capture_observation_value_marks_unsupported_numbers(value):
    assert _capture_observation_value(value) == {"type": type(value).__name__}


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
        "test_payment_ids": [payment.id],
        "test_series_ids": [],
        "test_user_ids": [],
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
            delete(BookingHold).where(
                BookingHold.payment_id.in_(records["test_payment_ids"])
            )
        )
        cleanup.execute(
            delete(Payment).where(Payment.id.in_(records["test_payment_ids"]))
        )
        cleanup.execute(
            delete(AppointmentSeries).where(
                AppointmentSeries.id.in_(records["test_series_ids"])
            )
        )
        cleanup.execute(delete(User).where(User.id.in_(records["test_user_ids"])))
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


def _create_test_role_token(records, role):
    db = SessionLocal()
    user = User(
        name=f"Reconciliation {role.value}",
        email=f"reconciliation-{role.value.lower()}-{uuid4()}@example.com",
        password_hash="test",
        role=role,
    )
    db.add(user)
    db.commit()
    user_id = user.id
    db.close()
    records["test_user_ids"].append(user_id)
    return create_access_token(user_id, role)


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


def test_conflicting_order_for_known_payment_is_reconciliation_candidate(
    webhook_records, monkeypatch
):
    records = webhook_records
    db = SessionLocal()
    payment = db.get(Payment, records["payment_id"])
    payment.provider_payment_id = records["provider_payment_id"]
    db.commit()
    db.close()
    _mock_signature(monkeypatch)

    response, _ = _post_webhook(
        records,
        monkeypatch,
        _captured_payload(records, order_id=f"order_{uuid4().hex}"),
    )

    payment, hold, appointments, events = _state(records)
    assert response.status_code == 200
    assert response.json()["status"] == PaymentWebhookEventStatus.FAILED
    assert payment.status == PaymentStatus.CREATED
    assert payment.provider_payment_id == records["provider_payment_id"]
    assert payment.appointment_id is None
    assert hold.status == BookingHoldStatus.ACTIVE
    assert appointments == []
    assert (
        events[0].capture_validation_failure
        == PaymentWebhookCaptureValidationFailure.PROVIDER_ORDER_ID_MISMATCH
    )

    db = SessionLocal()
    candidate = next(
        item
        for item in list_payment_reconciliation_candidates(
            db,
            stale_created_before=datetime.now(UTC) - timedelta(days=1),
        )
        if item.payment_id == records["payment_id"]
    )
    db.close()
    assert PaymentReconciliationReason.CAPTURE_VALIDATION_FAILED in candidate.reasons


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
    assert first.status_code == 200
    assert second.status_code == 200
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.appointment_id == appointments[0].id
    assert hold.status == BookingHoldStatus.CONVERTED
    assert len(appointments) == 1
    assert error_fragment in mismatch_event.error_message
    assert mismatch_event.capture_validation_failure is not None

    db = SessionLocal()
    candidate = next(
        item
        for item in list_payment_reconciliation_candidates(
            db,
            stale_created_before=datetime.now(UTC) - timedelta(days=1),
        )
        if item.payment_id == records["payment_id"]
    )
    db.close()
    assert candidate.appointment_id == appointments[0].id
    assert PaymentReconciliationReason.CAPTURE_VALIDATION_FAILED in candidate.reasons

    repeated, _ = _post_webhook(
        records,
        monkeypatch,
        _captured_payload(records, **overrides),
        event_id=mismatch_event.provider_event_id,
    )
    assert repeated.status_code == 200
    repeated_event = next(
        event
        for event in _state(records)[3]
        if event.provider_event_id == mismatch_event.provider_event_id
    )
    assert repeated_event.status == PaymentWebhookEventStatus.FAILED


def test_failed_local_payment_status_is_preserved(webhook_records, monkeypatch):
    records = webhook_records
    db = SessionLocal()
    payment = db.get(Payment, records["payment_id"])
    expected_provider_payment_id = payment.provider_payment_id
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
    assert payment.status == PaymentStatus.FAILED
    assert payment.provider_payment_id == expected_provider_payment_id
    assert payment.appointment_id is None
    assert hold.expires_at <= datetime.now(UTC)
    assert hold.status == BookingHoldStatus.ACTIVE
    assert appointments == []
    assert events[0].status == PaymentWebhookEventStatus.FAILED


@pytest.mark.parametrize(
    "status",
    [
        PaymentStatus.FAILED,
        PaymentStatus.REFUNDED,
        PaymentStatus.PARTIALLY_REFUNDED,
    ],
)
def test_conflicting_terminal_payment_status_is_preserved(
    webhook_records, monkeypatch, status
):
    records = webhook_records
    db = SessionLocal()
    payment = db.get(Payment, records["payment_id"])
    payment.status = status
    original_provider_payment_id = payment.provider_payment_id
    db.commit()
    db.close()
    _mock_signature(monkeypatch)

    response, _ = _post_webhook(records, monkeypatch)

    payment, hold, appointments, events = _state(records)
    assert response.status_code == 200
    assert response.json()["status"] == PaymentWebhookEventStatus.FAILED
    assert payment.status == status
    assert payment.provider_payment_id == original_provider_payment_id
    assert payment.appointment_id is None
    assert appointments == []
    assert hold.status == BookingHoldStatus.ACTIVE
    assert events[0].status == PaymentWebhookEventStatus.FAILED
    assert events[0].local_payment_state_conflict is True
    assert "Local payment state conflicts with provider capture" in (
        events[0].error_message
    )

    db = SessionLocal()
    candidate = next(
        item
        for item in list_payment_reconciliation_candidates(
            db,
            stale_created_before=datetime.now(UTC) - timedelta(days=1),
        )
        if item.payment_id == records["payment_id"]
    )
    db.close()
    assert PaymentReconciliationReason.LOCAL_PAYMENT_STATE_CONFLICT in (
        candidate.reasons
    )
    conflict_events = [
        event
        for event in candidate.webhook_events
        if event.local_payment_state_conflict
    ]
    assert len(conflict_events) == 1


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
        def verify_payment(self, *_args, **_kwargs):
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
            "payment_id": str(records["payment_id"]),
            "order_id": records["order_id"],
            "provider_payment_id": records["provider_payment_id"],
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
            "payment_id": str(records["payment_id"]),
            "order_id": records["order_id"],
            "provider_payment_id": records["provider_payment_id"],
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
    (
        "overrides",
        "failure",
        "expected_amount",
        "expected_currency",
        "error_fragment",
    ),
    [
        (
            {"amount": 1},
            PaymentWebhookCaptureValidationFailure.AMOUNT_MISMATCH,
            1,
            "INR",
            "Captured amount or currency does not match the local payment",
        ),
        (
            {"currency": "USD"},
            PaymentWebhookCaptureValidationFailure.CURRENCY_MISMATCH,
            2510,
            "USD",
            "Captured amount or currency does not match the local payment",
        ),
        (
            {"id": f"pay_{uuid4().hex}"},
            PaymentWebhookCaptureValidationFailure.PROVIDER_PAYMENT_ID_MISMATCH,
            2510,
            "INR",
            "Provider payment ID conflicts with the local payment",
        ),
    ],
)
def test_captured_payment_mismatches_are_recorded_for_reconciliation(
    webhook_records,
    monkeypatch,
    overrides,
    failure,
    expected_amount,
    expected_currency,
    error_fragment,
):
    records = webhook_records
    event_id = records["event_id"]
    if "id" in overrides:
        db = SessionLocal()
        db.get(Payment, records["payment_id"]).provider_payment_id = "pay_previous"
        db.commit()
        db.close()
    _mock_signature(monkeypatch)

    response, _ = _post_webhook(
        records, monkeypatch, _captured_payload(records, **overrides), event_id=event_id
    )

    assert response.status_code == 200
    payment, hold, appointments, events = _state(records)
    assert payment.status == PaymentStatus.CREATED
    assert payment.appointment_id is None
    assert payment.provider_payment_id == (
        "pay_previous" if "id" in overrides else None
    )
    assert hold.status == BookingHoldStatus.ACTIVE
    assert appointments == []
    assert events[0].status == PaymentWebhookEventStatus.FAILED
    assert error_fragment in events[0].error_message
    assert events[0].capture_validation_failure == failure.value
    assert events[0].capture_validation_details["amount"] == expected_amount
    assert events[0].capture_validation_details["currency"] == expected_currency
    failure_message = events[0].error_message

    repeated, _ = _post_webhook(
        records, monkeypatch, _captured_payload(records, **overrides), event_id=event_id
    )

    payment, hold, appointments, events = _state(records)
    assert repeated.status_code == 200
    assert events[0].status == PaymentWebhookEventStatus.FAILED
    assert events[0].error_message == failure_message
    assert payment.appointment_id is None
    assert appointments == []

    db = SessionLocal()
    candidate = next(
        item
        for item in list_payment_reconciliation_candidates(
            db,
            stale_created_before=datetime.now(UTC) + timedelta(days=1),
        )
        if item.payment_id == records["payment_id"]
    )
    db.close()
    assert PaymentReconciliationReason.CAPTURE_VALIDATION_FAILED in candidate.reasons
    assert candidate.webhook_events[0].capture_validation_failure == failure.value


@pytest.mark.parametrize(
    ("overrides", "failure"),
    [
        (
            {"id": None},
            PaymentWebhookCaptureValidationFailure.INVALID_PAYMENT_ID,
        ),
        (
            {"captured": False},
            PaymentWebhookCaptureValidationFailure.INVALID_CAPTURE_STATUS,
        ),
        (
            {"status": "authorized"},
            PaymentWebhookCaptureValidationFailure.INVALID_CAPTURE_STATUS,
        ),
    ],
)
def test_invalid_capture_data_is_not_persisted_as_capture(
    webhook_records, monkeypatch, overrides, failure
):
    records = webhook_records
    _mock_signature(monkeypatch)

    response, _ = _post_webhook(
        records, monkeypatch, _captured_payload(records, **overrides)
    )

    payment, hold, appointments, events = _state(records)
    assert response.status_code == 200
    assert payment.status == PaymentStatus.CREATED
    assert payment.provider_payment_id is None
    assert payment.appointment_id is None
    assert hold.status == BookingHoldStatus.ACTIVE
    assert appointments == []
    assert events[0].status == PaymentWebhookEventStatus.FAILED
    assert events[0].capture_validation_failure == failure.value
    assert events[0].capture_validation_details is not None

    db = SessionLocal()
    candidates = list_payment_reconciliation_candidates(
        db,
        stale_created_before=datetime.now(UTC) + timedelta(days=1),
    )
    db.close()
    candidate = next(item for item in candidates if item.payment_id == payment.id)
    assert PaymentReconciliationReason.CAPTURE_VALIDATION_FAILED in candidate.reasons


def test_expired_hold_records_captured_payment_without_appointment(
    webhook_records, monkeypatch
):
    records = webhook_records
    existing = Appointment(
        service_id=records["service_id"],
        provider_id=records["provider_id"],
        user_name="Existing booking",
        user_email="existing-expired-webhook@example.com",
        appointment_start=records["appointment_start"],
        appointment_end=records["appointment_start"] + timedelta(minutes=30),
        duration_minutes=30,
        buffer_time_minutes=10,
        status=AppointmentStatus.CONFIRMED,
    )
    db = SessionLocal()
    db.add(existing)
    hold = db.scalar(
        select(BookingHold).where(BookingHold.payment_id == records["payment_id"])
    )
    hold.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    existing_id = existing.id
    db.close()
    _mock_signature(monkeypatch)

    response, _ = _post_webhook(records, monkeypatch)

    assert response.status_code == 503
    payment, hold, appointments, events = _state(records)
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.provider_payment_id == records["provider_payment_id"]
    assert hold.status == BookingHoldStatus.EXPIRED
    assert len(appointments) == 1
    assert appointments[0].id == existing_id
    assert events[0].status == PaymentWebhookEventStatus.RETRYABLE


def test_failed_webhook_retries_after_expired_hold_slot_becomes_available(
    webhook_records, monkeypatch
):
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
    hold = db.scalar(
        select(BookingHold).where(BookingHold.payment_id == records["payment_id"])
    )
    hold.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    existing_id = existing.id
    db.close()
    _mock_signature(monkeypatch)

    response, _ = _post_webhook(records, monkeypatch)

    assert response.status_code == 503
    payment, hold, appointments, events = _state(records)
    assert payment.status == PaymentStatus.CAPTURED
    assert hold.status == BookingHoldStatus.EXPIRED
    assert len(appointments) == 1
    assert appointments[0].id == existing_id
    assert events[0].status == PaymentWebhookEventStatus.RETRYABLE
    assert events[0].error_message is not None

    db = SessionLocal()
    db.delete(db.get(Appointment, existing_id))
    db.commit()
    db.close()

    retry, _ = _post_webhook(records, monkeypatch)

    payment, hold, appointments, events = _state(records)
    assert retry.status_code == 200
    assert retry.json()["status"] == PaymentWebhookEventStatus.PROCESSED
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.appointment_id == appointments[0].id
    assert hold.status == BookingHoldStatus.CONVERTED
    assert len(appointments) == 1
    assert events[0].status == PaymentWebhookEventStatus.PROCESSED
    assert events[0].error_message is None


def test_failed_webhook_remains_retryable_until_slot_is_available(
    webhook_records, monkeypatch
):
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

    first, _ = _post_webhook(records, monkeypatch)
    second, _ = _post_webhook(records, monkeypatch)
    payment, hold, appointments, events = _state(records)
    assert first.status_code == second.status_code == 503
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.appointment_id is None
    assert hold.status == BookingHoldStatus.ACTIVE
    assert len(appointments) == 1
    assert events[0].status == PaymentWebhookEventStatus.RETRYABLE
    assert events[0].error_message is not None

    db = SessionLocal()
    db.delete(db.get(Appointment, existing_id))
    db.commit()
    db.close()

    recovered, _ = _post_webhook(records, monkeypatch)

    payment, hold, appointments, events = _state(records)
    assert recovered.status_code == 200
    assert recovered.json()["status"] == PaymentWebhookEventStatus.PROCESSED
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.appointment_id == appointments[0].id
    assert hold.status == BookingHoldStatus.CONVERTED
    assert len(appointments) == 1
    assert events[0].status == PaymentWebhookEventStatus.PROCESSED


def test_retryable_webhook_requires_exact_nonempty_provider_identity(
    webhook_records, monkeypatch
):
    records = webhook_records
    existing = Appointment(
        service_id=records["service_id"],
        provider_id=records["provider_id"],
        user_name="Existing webhook booking",
        user_email="existing-retry-guard@example.com",
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

    first, _ = _post_webhook(records, monkeypatch)
    assert first.status_code == 503
    assert _state(records)[3][0].status == PaymentWebhookEventStatus.RETRYABLE

    invalid_retries = [
        _captured_payload(records) | {"event": "payment.authorized"},
        _captured_payload(records, order_id="order_mismatch"),
        _captured_payload(records, id="pay_mismatch"),
        _captured_payload(records, order_id=None),
        _captured_payload(records, id=None),
        _captured_payload(records, order_id=""),
        _captured_payload(records, id=""),
    ]
    for invalid_payload in invalid_retries:
        response, _ = _post_webhook(
            records, monkeypatch, invalid_payload, event_id=records["event_id"]
        )
        payment, _hold, appointments, events = _state(records)
        assert response.status_code == 503
        assert events[0].status == PaymentWebhookEventStatus.RETRYABLE
        assert events[0].provider_order_id == records["order_id"]
        assert events[0].provider_payment_id == records["provider_payment_id"]
        assert payment.appointment_id is None
        assert len(appointments) == 1
        assert appointments[0].id == existing_id

    db = SessionLocal()
    db.delete(db.get(Appointment, existing_id))
    db.commit()
    db.close()

    recovered, _ = _post_webhook(records, monkeypatch)

    assert recovered.status_code == 200
    assert recovered.json()["status"] == PaymentWebhookEventStatus.PROCESSED
    assert len(_state(records)[2]) == 1


def test_permanent_provider_validation_failure_is_not_retried(
    webhook_records, monkeypatch
):
    records = webhook_records
    db = SessionLocal()
    provider = db.get(Provider, records["provider_id"])
    provider.availability_status = AvailabilityStatus.INACTIVE
    db.commit()
    db.close()
    _mock_signature(monkeypatch)

    first, _ = _post_webhook(records, monkeypatch)
    payment, hold, appointments, events = _state(records)
    assert first.status_code == 200
    assert events[0].status == PaymentWebhookEventStatus.FAILED
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.appointment_id is None
    assert hold.status == BookingHoldStatus.ACTIVE
    assert appointments == []

    repeated, _ = _post_webhook(records, monkeypatch)
    payment, _hold, appointments, events = _state(records)
    assert repeated.status_code == 200
    assert events[0].status == PaymentWebhookEventStatus.FAILED
    assert payment.appointment_id is None
    assert appointments == []


def test_already_linked_inconsistency_is_terminal(webhook_records, monkeypatch):
    records = webhook_records
    _mock_signature(monkeypatch)
    initial, _ = _post_webhook(records, monkeypatch)
    assert initial.status_code == 200
    appointment_id = _state(records)[0].appointment_id
    inconsistent_event_id = f"evt_{uuid4().hex}"
    records["test_event_ids"].append(inconsistent_event_id)
    original_get = Session.get
    calls = []

    def hide_linked_appointment(session, entity, ident, **kwargs):
        if entity is Appointment and ident == appointment_id:
            calls.append(ident)
            return None
        return original_get(session, entity, ident, **kwargs)

    monkeypatch.setattr(Session, "get", hide_linked_appointment)
    response, _ = _post_webhook(records, monkeypatch, event_id=inconsistent_event_id)
    assert response.status_code == 200
    failed_event = next(
        event
        for event in _state(records)[3]
        if event.provider_event_id == inconsistent_event_id
    )
    assert failed_event.status == PaymentWebhookEventStatus.FAILED
    assert calls == [appointment_id]

    repeated, _ = _post_webhook(records, monkeypatch, event_id=inconsistent_event_id)
    assert repeated.status_code == 200
    assert calls == [appointment_id]


def test_expired_hold_is_confirmed_only_after_fresh_availability_check(
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

    payment, hold, appointments, events = _state(records)
    assert response.status_code == 200
    assert response.json()["status"] == PaymentWebhookEventStatus.PROCESSED
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.appointment_id == appointments[0].id
    assert hold.status == BookingHoldStatus.CONVERTED
    assert len(appointments) == 1
    assert events[0].status == PaymentWebhookEventStatus.PROCESSED


def test_concurrent_duplicate_webhooks_create_one_appointment(
    webhook_records, monkeypatch
):
    records = webhook_records
    _mock_signature(monkeypatch)
    barrier = Barrier(2)

    def post_duplicate():
        barrier.wait(timeout=5)
        return _post_webhook(records, monkeypatch)[0]

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _index: post_duplicate(), range(2)))

    payment, hold, appointments, events = _state(records)
    assert [response.status_code for response in responses] == [200, 200]
    assert all(
        response.json()["status"] == PaymentWebhookEventStatus.PROCESSED
        for response in responses
    )
    assert len(appointments) == 1
    assert payment.appointment_id == appointments[0].id
    assert hold.status == BookingHoldStatus.CONVERTED
    assert len(events) == 1
    assert events[0].status == PaymentWebhookEventStatus.PROCESSED


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
    commit_count = 0

    def fail_commit(session):
        nonlocal commit_count
        commit_count += 1
        if commit_count == 1:
            raise OperationalError("commit", {}, RuntimeError("database unavailable"))
        original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_commit)
    response, _ = _post_webhook(records, monkeypatch)
    monkeypatch.setattr(Session, "commit", original_commit)

    assert response.status_code == 503
    payment, hold, appointments, events = _state(records)
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.provider_payment_id == records["provider_payment_id"]
    assert payment.appointment_id is None
    assert hold.status == BookingHoldStatus.ACTIVE
    assert appointments == []
    assert len(events) == 1
    assert events[0].status == PaymentWebhookEventStatus.RETRYABLE

    retry, _ = _post_webhook(records, monkeypatch)
    payment, hold, appointments, events = _state(records)
    assert retry.status_code == 200
    assert retry.json()["status"] == PaymentWebhookEventStatus.PROCESSED
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.appointment_id == appointments[0].id
    assert hold.status == BookingHoldStatus.CONVERTED
    assert len(appointments) == 1
    assert events[0].status == PaymentWebhookEventStatus.PROCESSED


def test_database_failure_during_fallback_leaves_fulfillment_retryable(
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
    assert payment.appointment_id is None
    assert hold.status == BookingHoldStatus.ACTIVE
    assert appointments == []
    assert events == []

    retry, _ = _post_webhook(records, monkeypatch)
    payment, hold, appointments, events = _state(records)
    assert retry.status_code == 200
    assert retry.json()["status"] == PaymentWebhookEventStatus.PROCESSED
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.appointment_id == appointments[0].id
    assert hold.status == BookingHoldStatus.CONVERTED
    assert len(appointments) == 1
    assert events[0].status == PaymentWebhookEventStatus.PROCESSED


def test_retryable_event_rejects_a_changed_payment_identity(
    webhook_records, monkeypatch
):
    records = webhook_records
    _mock_signature(monkeypatch)
    original_commit = Session.commit
    commit_count = 0

    def fail_fulfillment_commit(session):
        nonlocal commit_count
        commit_count += 1
        if commit_count == 1:
            raise OperationalError("commit", {}, RuntimeError("database unavailable"))
        original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_fulfillment_commit)
    failed, _ = _post_webhook(records, monkeypatch)
    monkeypatch.setattr(Session, "commit", original_commit)

    changed_identity, _ = _post_webhook(
        records,
        monkeypatch,
        _captured_payload(records, id=f"pay_{uuid4().hex}"),
    )
    payment, hold, appointments, events = _state(records)

    assert failed.status_code == 503
    assert changed_identity.status_code == 503
    assert "webhook processing will be retried" in (
        changed_identity.json()["detail"].lower()
    )
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.provider_payment_id == records["provider_payment_id"]
    assert payment.appointment_id is None
    assert hold.status == BookingHoldStatus.ACTIVE
    assert appointments == []
    assert events[0].status == PaymentWebhookEventStatus.RETRYABLE


def test_uncertain_commit_preserves_successful_fulfillment(
    webhook_records, monkeypatch
):
    records = webhook_records
    _mock_signature(monkeypatch)
    original_commit = Session.commit
    commit_count = 0

    def commit_then_raise(session):
        nonlocal commit_count
        commit_count += 1
        original_commit(session)
        if commit_count == 1:
            raise OperationalError("commit", {}, RuntimeError("connection lost"))

    monkeypatch.setattr(Session, "commit", commit_then_raise)
    response, _ = _post_webhook(records, monkeypatch)
    monkeypatch.setattr(Session, "commit", original_commit)

    assert response.status_code == 200
    assert response.json()["status"] == PaymentWebhookEventStatus.PROCESSED
    payment, hold, appointments, events = _state(records)
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.appointment_id == appointments[0].id
    assert hold.status == BookingHoldStatus.CONVERTED
    assert len(appointments) == 1
    assert events[0].status == PaymentWebhookEventStatus.PROCESSED


def test_webhook_requires_no_customer_authentication(webhook_records, monkeypatch):
    records = webhook_records
    _mock_signature(monkeypatch)

    response, _ = _post_webhook(records, monkeypatch)

    assert response.status_code == 200
    assert len(_state(records)[2]) == 1


def test_reconciliation_lists_captured_unlinked_and_all_matching_events(
    webhook_records,
):
    records = webhook_records
    now = datetime.now(UTC)
    db = SessionLocal()
    payment = db.get(Payment, records["payment_id"])
    payment.status = PaymentStatus.CAPTURED
    payment.provider_payment_id = records["provider_payment_id"]
    hold = db.scalar(
        select(BookingHold).where(BookingHold.payment_id == records["payment_id"])
    )
    unrelated_payment = Payment(
        customer_id=records["customer_id"],
        amount=2510,
        currency="INR",
        status=PaymentStatus.FAILED,
        provider=PaymentProvider.RAZORPAY,
        provider_order_id=f"order_{uuid4().hex}",
        provider_payment_id=f"pay_{uuid4().hex}",
    )
    db.add(unrelated_payment)
    db.flush()
    unrelated_payment_id = unrelated_payment.id
    records["test_payment_ids"].append(unrelated_payment_id)

    matching_events = [
        PaymentWebhookEvent(
            provider_event_id=f"evt_{uuid4().hex}",
            event_type="payment.captured",
            provider_order_id=records["order_id"],
            provider_payment_id=records["provider_payment_id"],
            status=PaymentWebhookEventStatus.RETRYABLE,
            created_at=now - timedelta(minutes=2),
            processed_at=now - timedelta(minutes=2),
        ),
        PaymentWebhookEvent(
            provider_event_id=f"evt_{uuid4().hex}",
            event_type="payment.captured",
            provider_order_id=records["order_id"],
            provider_payment_id=f"pay_{uuid4().hex}",
            status=PaymentWebhookEventStatus.FAILED,
            error_message="Captured amount or currency does not match the local payment",
            created_at=now - timedelta(minutes=1),
            processed_at=now - timedelta(minutes=1),
        ),
        PaymentWebhookEvent(
            provider_event_id=f"evt_{uuid4().hex}",
            event_type="payment.captured",
            provider_order_id=f"order_{uuid4().hex}",
            provider_payment_id=records["provider_payment_id"],
            status=PaymentWebhookEventStatus.FAILED,
            error_message="Provider payment ID conflicts with the local payment",
            created_at=now,
            processed_at=now,
        ),
        PaymentWebhookEvent(
            provider_event_id=f"evt_{uuid4().hex}",
            event_type="payment.captured",
            provider_order_id=records["order_id"],
            provider_payment_id=records["provider_payment_id"],
            status=PaymentWebhookEventStatus.FAILED,
            error_message="Captured amount or currency does not match the local payment",
            created_at=now,
            processed_at=now,
        ),
    ]
    unrelated_event = PaymentWebhookEvent(
        provider_event_id=f"evt_{uuid4().hex}",
        event_type="payment.captured",
        provider_order_id=f"order_{uuid4().hex}",
        provider_payment_id=f"pay_{uuid4().hex}",
        status=PaymentWebhookEventStatus.FAILED,
        created_at=now,
        processed_at=now,
    )
    matching_event_ids = {event.provider_event_id for event in matching_events}
    hold_id = hold.id
    expected_event_states = {
        event.provider_event_id: (event.status, event.error_message)
        for event in [*matching_events, unrelated_event]
    }
    db.add_all([*matching_events, unrelated_event])
    records["test_event_ids"].extend(
        event.provider_event_id for event in [*matching_events, unrelated_event]
    )
    db.commit()
    before = (
        payment.status,
        payment.provider_payment_id,
        payment.appointment_id,
        hold.status,
        hold.updated_at,
        len(_state(records)[2]),
    )
    db.close()

    db = SessionLocal()
    candidates = list_payment_reconciliation_candidates(
        db,
        stale_created_before=now - timedelta(days=1),
        as_of=now,
    )
    db.close()
    assert all(item.payment_id != unrelated_payment_id for item in candidates)

    candidate = next(
        item for item in candidates if item.payment_id == records["payment_id"]
    )
    assert candidate.status == PaymentStatus.CAPTURED
    assert candidate.provider_verification_required is True
    assert candidate.booking_holds[0].id == hold_id
    assert len(candidate.webhook_events) == 4
    assert {event.provider_event_id for event in candidate.webhook_events} == (
        matching_event_ids
    )
    assert all(event.status and event.created_at for event in candidate.webhook_events)
    assert any(event.error_message for event in candidate.webhook_events)
    assert {
        PaymentReconciliationReason.CAPTURED_UNLINKED,
        PaymentReconciliationReason.RETRYABLE_WEBHOOK_EVENT,
        PaymentReconciliationReason.FAILED_WEBHOOK_EVENT,
        PaymentReconciliationReason.MISMATCHED_PROVIDER_ORDER_ID,
        PaymentReconciliationReason.MISMATCHED_PROVIDER_PAYMENT_ID,
    }.issubset(set(candidate.reasons))
    assert all(
        reason.value != "amount_currency_mismatch" for reason in candidate.reasons
    )

    payment_after, hold_after, appointments, events_after = _state(records)
    assert (
        payment_after.status,
        payment_after.provider_payment_id,
        payment_after.appointment_id,
        hold_after.status,
        hold_after.updated_at,
        len(appointments),
    ) == before
    assert {
        event.provider_event_id: (event.status, event.error_message)
        for event in events_after
    } == expected_event_states


def test_reconciliation_retains_events_with_one_conflicting_provider_id(
    webhook_records,
):
    records = webhook_records
    now = datetime.now(UTC)
    matching_order = PaymentWebhookEvent(
        provider_event_id=f"evt_{uuid4().hex}",
        event_type="payment.captured",
        provider_order_id=records["order_id"],
        provider_payment_id=f"pay_{uuid4().hex}",
        status=PaymentWebhookEventStatus.FAILED,
        created_at=now,
        processed_at=now,
    )
    matching_payment = PaymentWebhookEvent(
        provider_event_id=f"evt_{uuid4().hex}",
        event_type="payment.captured",
        provider_order_id=f"order_{uuid4().hex}",
        provider_payment_id=records["provider_payment_id"],
        status=PaymentWebhookEventStatus.RETRYABLE,
        created_at=now + timedelta(seconds=1),
        processed_at=now + timedelta(seconds=1),
    )
    matching_order_event_id = matching_order.provider_event_id
    matching_order_payment_id = matching_order.provider_payment_id
    matching_payment_event_id = matching_payment.provider_event_id
    matching_payment_order_id = matching_payment.provider_order_id
    db = SessionLocal()
    payment = db.get(Payment, records["payment_id"])
    payment.status = PaymentStatus.CAPTURED
    payment.provider_payment_id = records["provider_payment_id"]
    db.add_all([matching_order, matching_payment])
    expected_event_ids = {
        matching_order_event_id,
        matching_payment_event_id,
    }
    records["test_event_ids"].extend(expected_event_ids)
    db.commit()
    db.close()

    db = SessionLocal()
    candidate = next(
        item
        for item in list_payment_reconciliation_candidates(
            db,
            stale_created_before=now - timedelta(days=1),
            as_of=now,
        )
        if item.payment_id == records["payment_id"]
    )
    db.close()

    events_by_id = {
        event.provider_event_id: event for event in candidate.webhook_events
    }
    assert set(events_by_id) == expected_event_ids
    assert (
        events_by_id[matching_order_event_id].provider_order_id == records["order_id"]
    )
    assert (
        events_by_id[matching_order_event_id].provider_payment_id
        == matching_order_payment_id
    )
    assert (
        events_by_id[matching_payment_event_id].provider_order_id
        == matching_payment_order_id
    )
    assert (
        events_by_id[matching_payment_event_id].provider_payment_id
        == records["provider_payment_id"]
    )
    assert PaymentReconciliationReason.MISMATCHED_PROVIDER_PAYMENT_ID in (
        candidate.reasons
    )
    assert PaymentReconciliationReason.MISMATCHED_PROVIDER_ORDER_ID in (
        candidate.reasons
    )
    assert PaymentReconciliationReason.FAILED_WEBHOOK_EVENT in candidate.reasons
    assert PaymentReconciliationReason.RETRYABLE_WEBHOOK_EVENT in candidate.reasons


@pytest.mark.parametrize(
    ("hold_status", "hold_expiry"),
    [
        (BookingHoldStatus.EXPIRED, timedelta(days=-1)),
        (BookingHoldStatus.RELEASED, timedelta(days=-1)),
        (BookingHoldStatus.ACTIVE, timedelta(days=-1)),
    ],
)
def test_reconciliation_lists_stale_created_payment_with_expired_or_released_hold(
    webhook_records, hold_status, hold_expiry
):
    records = webhook_records
    now = datetime.now(UTC)
    db = SessionLocal()
    payment = db.get(Payment, records["payment_id"])
    payment.created_at = now - timedelta(days=2)
    hold = db.scalar(
        select(BookingHold).where(BookingHold.payment_id == records["payment_id"])
    )
    hold.status = hold_status
    hold.expires_at = now + hold_expiry
    db.commit()
    original_payment_state = (
        payment.status,
        payment.created_at,
        payment.appointment_id,
    )
    original_hold_state = (hold.status, hold.expires_at, hold.updated_at)
    db.close()

    db = SessionLocal()
    candidates = list_payment_reconciliation_candidates(
        db,
        stale_created_before=now - timedelta(days=1),
        as_of=now,
    )
    db.close()

    candidate = next(
        item for item in candidates if item.payment_id == records["payment_id"]
    )
    assert candidate.status == PaymentStatus.CREATED
    assert candidate.provider_verification_required is True
    assert PaymentReconciliationReason.STALE_CREATED_NO_CAPTURE_EVIDENCE in (
        candidate.reasons
    )
    expected_hold_reason = (
        PaymentReconciliationReason.RELEASED_HOLD
        if hold_status == BookingHoldStatus.RELEASED
        else PaymentReconciliationReason.EXPIRED_HOLD
    )
    assert expected_hold_reason in candidate.reasons
    payment_after, hold_after, appointments, _ = _state(records)
    assert (
        payment_after.status,
        payment_after.created_at,
        payment_after.appointment_id,
    ) == original_payment_state
    assert (hold_after.status, hold_after.expires_at, hold_after.updated_at) == (
        *original_hold_state,
    )
    assert appointments == []


def test_reconciliation_requires_explicit_stale_cutoff_and_bounds_results(
    webhook_records,
):
    records = webhook_records
    now = datetime.now(UTC)
    db = SessionLocal()
    payment = db.get(Payment, records["payment_id"])
    payment.status = PaymentStatus.CREATED
    payment.created_at = now - timedelta(hours=1)
    hold = db.scalar(
        select(BookingHold).where(BookingHold.payment_id == records["payment_id"])
    )
    hold.status = BookingHoldStatus.EXPIRED
    hold.expires_at = now - timedelta(minutes=1)

    another_payment = Payment(
        customer_id=payment.customer_id,
        amount=2510,
        currency="INR",
        status=PaymentStatus.CAPTURED,
        provider=PaymentProvider.RAZORPAY,
        provider_order_id=f"order_{uuid4().hex}",
        provider_payment_id=f"pay_{uuid4().hex}",
        created_at=now - timedelta(days=3),
    )
    db.add(another_payment)
    db.flush()
    another_payment_id = another_payment.id
    records["test_payment_ids"].append(another_payment_id)
    db.commit()
    db.close()

    db = SessionLocal()
    before_cutoff = list_payment_reconciliation_candidates(
        db,
        stale_created_before=now - timedelta(days=2),
        as_of=now,
    )
    bounded = list_payment_reconciliation_candidates(
        db,
        stale_created_before=now - timedelta(days=2),
        as_of=now,
        limit=1,
    )
    db.close()

    assert all(
        candidate.payment_id != records["payment_id"] for candidate in before_cutoff
    )
    assert any(
        candidate.payment_id == another_payment_id for candidate in before_cutoff
    )
    assert len(bounded) == 1
    assert bounded[0].payment_id != records["payment_id"]
    assert bounded[0].provider_verification_required is True


def test_reconciliation_excludes_stale_created_payments_without_eligible_hold(
    webhook_records,
):
    records = webhook_records
    now = datetime.now(UTC)
    db = SessionLocal()
    payment = db.get(Payment, records["payment_id"])
    payment.status = PaymentStatus.CREATED
    payment.created_at = now - timedelta(days=3)
    hold = db.scalar(
        select(BookingHold).where(BookingHold.payment_id == records["payment_id"])
    )
    hold.status = BookingHoldStatus.ACTIVE
    hold.expires_at = now + timedelta(days=1)

    stale_without_hold = Payment(
        customer_id=records["customer_id"],
        amount=2510,
        currency="INR",
        status=PaymentStatus.CREATED,
        provider=PaymentProvider.RAZORPAY,
        provider_order_id=f"order_{uuid4().hex}",
        created_at=now - timedelta(days=3),
    )
    db.add(stale_without_hold)
    db.flush()
    stale_without_hold_id = stale_without_hold.id
    records["test_payment_ids"].append(stale_without_hold_id)

    stale_with_active_hold = Payment(
        customer_id=records["customer_id"],
        amount=2510,
        currency="INR",
        status=PaymentStatus.CREATED,
        provider=PaymentProvider.RAZORPAY,
        provider_order_id=f"order_{uuid4().hex}",
        created_at=now - timedelta(days=3),
    )
    db.add(stale_with_active_hold)
    db.flush()
    stale_with_active_hold_id = stale_with_active_hold.id
    records["test_payment_ids"].append(stale_with_active_hold_id)
    active_hold = BookingHold(
        customer_id=records["customer_id"],
        service_id=records["service_id"],
        provider_id=records["provider_id"],
        user_name="Webhook Recipient",
        user_email="webhook-recipient@example.com",
        user_phone="+15550003333",
        appointment_start=records["appointment_start"],
        appointment_end=records["appointment_start"] + timedelta(minutes=30),
        expires_at=now + timedelta(days=1),
        status=BookingHoldStatus.ACTIVE,
        payment_id=stale_with_active_hold_id,
    )
    db.add(active_hold)
    db.commit()
    db.close()

    db = SessionLocal()
    candidates = list_payment_reconciliation_candidates(
        db,
        stale_created_before=now - timedelta(days=1),
        as_of=now,
    )
    db.close()

    candidate_ids = {candidate.payment_id for candidate in candidates}
    assert records["payment_id"] not in candidate_ids
    assert stale_without_hold_id not in candidate_ids
    assert stale_with_active_hold_id not in candidate_ids


def test_reconciliation_excludes_captured_payment_linked_to_series(webhook_records):
    records = webhook_records
    now = datetime.now(UTC)
    db = SessionLocal()
    series = AppointmentSeries(
        customer_id=records["customer_id"],
        provider_id=records["provider_id"],
        service_id=records["service_id"],
        frequency=AppointmentSeriesFrequency.WEEKLY,
        interval=1,
        start_date=date.today() + timedelta(days=7),
        local_start_time=time(10),
        timezone="UTC",
        end_mode=AppointmentSeriesEndMode.COUNT,
        occurrence_count=2,
        status=AppointmentSeriesStatus.ACTIVE,
    )
    db.add(series)
    db.flush()
    series_id = series.id
    records["test_series_ids"].append(series_id)
    payment = db.get(Payment, records["payment_id"])
    payment.status = PaymentStatus.CAPTURED
    payment.series_id = series_id
    db.commit()
    db.close()

    db = SessionLocal()
    candidates = list_payment_reconciliation_candidates(
        db,
        stale_created_before=now - timedelta(days=1),
        as_of=now,
    )
    db.close()

    assert all(
        candidate.payment_id != records["payment_id"] for candidate in candidates
    )


def test_reconciliation_flags_missing_provider_ids_and_validates_arguments(
    webhook_records,
):
    records = webhook_records
    db = SessionLocal()
    payment = db.get(Payment, records["payment_id"])
    payment.status = PaymentStatus.CAPTURED
    payment.provider_order_id = None
    payment.provider_payment_id = None
    db.commit()
    db.close()

    db = SessionLocal()
    candidates = list_payment_reconciliation_candidates(
        db,
        stale_created_before=datetime.now(UTC) - timedelta(days=1),
    )
    with pytest.raises(ValueError, match="limit"):
        list_payment_reconciliation_candidates(
            db,
            stale_created_before=datetime.now(UTC) - timedelta(days=1),
            limit=501,
        )
    with pytest.raises(ValueError, match="timezone"):
        list_payment_reconciliation_candidates(
            db,
            stale_created_before=datetime.now(),
        )
    db.close()

    candidate = next(
        item for item in candidates if item.payment_id == records["payment_id"]
    )
    assert (
        PaymentReconciliationReason.MISSING_LOCAL_PROVIDER_ORDER_ID in candidate.reasons
    )
    assert (
        PaymentReconciliationReason.MISSING_LOCAL_PROVIDER_PAYMENT_ID
        in candidate.reasons
    )
    assert candidate.webhook_events == []


def test_admin_payment_reconciliation_returns_candidates_without_mutation(
    webhook_records,
):
    records = webhook_records
    admin_token = _create_test_role_token(records, UserRole.ADMIN)
    now = datetime.now(UTC)
    db = SessionLocal()
    payment = db.get(Payment, records["payment_id"])
    payment.status = PaymentStatus.CAPTURED
    payment.provider_payment_id = records["provider_payment_id"]
    holds = db.scalars(
        select(BookingHold).where(BookingHold.payment_id == records["payment_id"])
    ).all()
    cutoff = now - timedelta(days=1)
    stale_created_payment = Payment(
        customer_id=records["customer_id"],
        amount=2510,
        currency="INR",
        status=PaymentStatus.CREATED,
        provider=PaymentProvider.RAZORPAY,
        provider_order_id=f"order_{uuid4().hex}",
        created_at=cutoff - timedelta(days=1),
    )
    recent_created_payment = Payment(
        customer_id=records["customer_id"],
        amount=2510,
        currency="INR",
        status=PaymentStatus.CREATED,
        provider=PaymentProvider.RAZORPAY,
        provider_order_id=f"order_{uuid4().hex}",
        created_at=now,
    )
    db.add_all([stale_created_payment, recent_created_payment])
    db.flush()
    stale_created_payment_id = stale_created_payment.id
    recent_created_payment_id = recent_created_payment.id
    records["test_payment_ids"].extend(
        [stale_created_payment_id, recent_created_payment_id]
    )
    for candidate_payment in [stale_created_payment, recent_created_payment]:
        db.add(
            BookingHold(
                customer_id=records["customer_id"],
                service_id=records["service_id"],
                provider_id=records["provider_id"],
                user_name="Webhook Recipient",
                user_email="webhook-recipient@example.com",
                user_phone="+15550003333",
                appointment_start=records["appointment_start"],
                appointment_end=records["appointment_start"] + timedelta(minutes=30),
                expires_at=now - timedelta(hours=1),
                status=BookingHoldStatus.EXPIRED,
                payment_id=candidate_payment.id,
            )
        )
    event_records = [
        PaymentWebhookEvent(
            provider_event_id=f"evt_{uuid4().hex}",
            event_type="payment.captured",
            provider_order_id=records["order_id"],
            provider_payment_id=records["provider_payment_id"],
            status=PaymentWebhookEventStatus.RETRYABLE,
            error_message="First investigation detail",
            created_at=now - timedelta(minutes=2),
            processed_at=now - timedelta(minutes=2),
        ),
        PaymentWebhookEvent(
            provider_event_id=f"evt_{uuid4().hex}",
            event_type="payment.captured",
            provider_order_id=f"order_{uuid4().hex}",
            provider_payment_id=records["provider_payment_id"],
            status=PaymentWebhookEventStatus.FAILED,
            error_message="Second investigation detail",
            created_at=now - timedelta(minutes=1),
            processed_at=now - timedelta(minutes=1),
        ),
    ]
    db.add_all(event_records)
    records["test_event_ids"].extend(event.provider_event_id for event in event_records)
    db.commit()
    hold_id = holds[0].id
    original_payment_state = (
        payment.status,
        payment.provider_payment_id,
        payment.appointment_id,
    )
    original_hold_state = (holds[0].status, holds[0].updated_at)
    original_event_state = {
        event.provider_event_id: (event.status, event.error_message)
        for event in event_records
    }
    db.close()

    response = client.get(
        "/api/admin/payment-reconciliation",
        params={
            "stale_created_before": cutoff.isoformat(),
            "limit": 17,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    candidates = response.json()
    candidate_payment_ids = {item["payment_id"] for item in candidates}
    assert str(records["payment_id"]) in candidate_payment_ids
    assert str(stale_created_payment_id) in candidate_payment_ids
    assert str(recent_created_payment_id) not in candidate_payment_ids
    candidate = next(
        item for item in candidates if item["payment_id"] == str(records["payment_id"])
    )
    assert candidate["provider_verification_required"] is True
    assert candidate["booking_holds"][0]["id"] == str(hold_id)
    assert len(candidate["webhook_events"]) == 2
    assert {event["provider_event_id"] for event in candidate["webhook_events"]} == set(
        original_event_state
    )
    assert {event["error_message"] for event in candidate["webhook_events"]} == {
        "First investigation detail",
        "Second investigation detail",
    }

    db = SessionLocal()
    payment_after = db.get(Payment, records["payment_id"])
    hold_after = db.get(BookingHold, hold_id)
    event_after = db.scalars(
        select(PaymentWebhookEvent).where(
            PaymentWebhookEvent.provider_event_id.in_(records["test_event_ids"])
        )
    ).all()
    appointments_after = db.scalars(
        select(Appointment).where(Appointment.provider_id == records["provider_id"])
    ).all()
    assert (
        payment_after.status,
        payment_after.provider_payment_id,
        payment_after.appointment_id,
    ) == original_payment_state
    assert (hold_after.status, hold_after.updated_at) == original_hold_state
    assert {
        event.provider_event_id: (event.status, event.error_message)
        for event in event_after
    } == original_event_state
    assert appointments_after == []
    db.close()


@pytest.mark.parametrize("role", [UserRole.CUSTOMER, UserRole.PROVIDER])
def test_admin_payment_reconciliation_denies_non_admin_roles(webhook_records, role):
    token = _create_test_role_token(webhook_records, role)
    response = client.get(
        "/api/admin/payment-reconciliation",
        params={"stale_created_before": datetime.now(UTC).isoformat()},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_admin_payment_reconciliation_requires_authentication(webhook_records):
    response = client.get(
        "/api/admin/payment-reconciliation",
        params={"stale_created_before": datetime.now(UTC).isoformat()},
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("params", "expected_detail"),
    [
        ({}, None),
        ({"stale_created_before": "2026-10-01T00:00:00"}, "timezone"),
        (
            {
                "stale_created_before": "2026-10-01T00:00:00Z",
                "limit": 0,
            },
            None,
        ),
        (
            {
                "stale_created_before": "2026-10-01T00:00:00Z",
                "limit": 501,
            },
            None,
        ),
    ],
)
def test_admin_payment_reconciliation_validates_cutoff_and_limit(
    webhook_records, params, expected_detail
):
    token = _create_test_role_token(webhook_records, UserRole.ADMIN)
    response = client.get(
        "/api/admin/payment-reconciliation",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    if expected_detail:
        assert expected_detail in response.text
