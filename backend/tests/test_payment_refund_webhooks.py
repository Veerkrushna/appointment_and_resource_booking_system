import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

import app.models  # noqa: F401
from app.db.database import SessionLocal
from app.main import app
from app.models.payment import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    PaymentWebhookEvent,
    PaymentWebhookEventStatus,
)
from app.models.refund import PaymentRefundStatus, Refund
from app.models.user import User, UserRole
from app.services.payment_refunds import (
    RefundValidationError,
    reconcile_processing_refund,
)
from app.services.payment_webhooks import process_payment_webhook
from app.services.razorpay import RazorpayIntegrationError

client = TestClient(app)


@pytest.fixture
def refund_webhook_records():
    FakeRazorpayService.provider_payment_id = None
    FakeRazorpayService.provider_order_id = None
    FakeRazorpayService.payment_lookup_error = False
    FakeRazorpayService.refund_lookup_error = False
    FakeRazorpayService.refund_status = "processed"
    FakeRazorpayService.payment_amount_refunded = 12500
    FakeRazorpayService.refund_changes = {}
    FakeRazorpayService.payment_changes = {}
    FakeRazorpayService.fetch_payment_calls = 0
    FakeRazorpayService.fetch_refund_calls = 0
    FakeRazorpayService.fetch_payment_refunds_calls = 0
    token = uuid4()
    db = SessionLocal()
    customer = User(
        name=f"Refund Webhook {token}",
        email=f"refund-webhook-{token}@example.com",
        password_hash="test",
        role=UserRole.CUSTOMER,
    )
    db.add(customer)
    db.flush()
    payment = Payment(
        customer_id=customer.id,
        amount=12500,
        currency="INR",
        status=PaymentStatus.CAPTURED,
        provider=PaymentProvider.RAZORPAY,
        provider_order_id=f"order_{token.hex}",
        provider_payment_id=f"pay_{token.hex}",
    )
    db.add(payment)
    db.flush()
    provider_refund_id = f"rfnd_{token.hex}"
    refund = Refund(
        payment_id=payment.id,
        amount=12500,
        currency="INR",
        status=PaymentRefundStatus.PROCESSING,
        razorpay_refund_id=provider_refund_id,
        idempotency_key=f"refund-key-{token}",
        reason="Test refund",
    )
    db.add(refund)
    db.commit()
    records = {
        "payment_id": payment.id,
        "customer_id": customer.id,
        "provider_payment_id": payment.provider_payment_id,
        "provider_order_id": payment.provider_order_id,
        "refund_id": refund.id,
        "provider_refund_id": provider_refund_id,
        "event_ids": [],
        "token": token,
    }
    FakeRazorpayService.provider_payment_id = payment.provider_payment_id
    FakeRazorpayService.provider_order_id = payment.provider_order_id
    db.close()

    try:
        yield records
    finally:
        cleanup = SessionLocal()
        cleanup.execute(
            delete(PaymentWebhookEvent).where(
                PaymentWebhookEvent.provider_event_id.in_(records["event_ids"])
            )
        )
        cleanup.execute(delete(Refund).where(Refund.id == records["refund_id"]))
        cleanup.execute(delete(Payment).where(Payment.id == records["payment_id"]))
        cleanup.execute(delete(User).where(User.id == records["customer_id"]))
        cleanup.commit()
        cleanup.close()


class FakeRazorpayService:
    provider_payment_id = None
    provider_order_id = None
    payment_lookup_error = False
    refund_lookup_error = False
    refund_status = "processed"
    payment_amount_refunded = 12500
    refund_changes = {}
    payment_changes = {}
    fetch_payment_calls = 0
    fetch_refund_calls = 0
    fetch_payment_refunds_calls = 0

    def verify_webhook_signature(self, _raw_body, signature):
        return signature == "valid-signature"

    def fetch_payment(self, payment_id):
        cls = type(self)
        cls.fetch_payment_calls += 1
        if cls.payment_lookup_error:
            raise RazorpayIntegrationError("payment lookup unavailable")
        return {
            "id": payment_id,
            "order_id": cls.provider_order_id,
            "status": "captured",
            "amount": 12500,
            "amount_refunded": cls.payment_amount_refunded,
            "currency": "INR",
            **cls.payment_changes,
        }

    def fetch_refund(self, payment_id, refund_id):
        cls = type(self)
        cls.fetch_refund_calls += 1
        if cls.refund_lookup_error:
            raise RazorpayIntegrationError("refund lookup unavailable")
        return {
            "id": refund_id,
            "payment_id": payment_id,
            "amount": 12500,
            "currency": "INR",
            "status": cls.refund_status,
            **cls.refund_changes,
        }

    def fetch_payment_refunds(self, _payment_id):
        type(self).fetch_payment_refunds_calls += 1
        return {"entity": "collection", "items": []}


def _payload(records, event_type="refund.processed", **changes):
    refund_entity = {
        "id": records["provider_refund_id"],
        "entity": "refund",
        "amount": 12500,
        "currency": "INR",
        "payment_id": records["provider_payment_id"],
        "status": "processed",
    }
    refund_entity.update(changes)
    return {
        "entity": "event",
        "event": event_type,
        "contains": ["refund", "payment"],
        "payload": {
            "refund": {"entity": refund_entity},
            "payment": {
                "entity": {
                    "id": records["provider_payment_id"],
                    "entity": "payment",
                    "amount": 12500,
                    "currency": "INR",
                    "status": "captured",
                    "order_id": records["provider_order_id"],
                    "amount_refunded": 12500,
                }
            },
        },
    }


def _post(records, monkeypatch, payload, *, event_id=None, signature="valid-signature"):
    event_id = event_id or f"evt_{uuid4().hex}"
    records["event_ids"].append(event_id)
    FakeRazorpayService.provider_payment_id = records["provider_payment_id"]
    FakeRazorpayService.provider_order_id = records["provider_order_id"]
    monkeypatch.setattr("app.api.routes.payments.RazorpayService", FakeRazorpayService)
    monkeypatch.setattr(
        "app.services.razorpay.RazorpayService",
        FakeRazorpayService,
    )
    return client.post(
        "/api/payments/webhook",
        content=json.dumps(payload).encode(),
        headers={
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": event_id,
            "Content-Type": "application/json",
        },
    )


def _refund_and_events(records):
    db = SessionLocal()
    refund = db.get(Refund, records["refund_id"])
    events = db.scalars(
        select(PaymentWebhookEvent).where(
            PaymentWebhookEvent.provider_event_id.in_(records["event_ids"])
        )
    ).all()
    result = refund.status, refund.razorpay_refund_id, events
    db.close()
    return result


@pytest.mark.parametrize(
    ("event_type", "provider_status", "expected"),
    [
        ("refund.created", "pending", PaymentRefundStatus.PROCESSING),
        ("refund.processed", "processed", PaymentRefundStatus.PROCESSED),
        ("refund.failed", "failed", PaymentRefundStatus.FAILED),
    ],
)
def test_supported_refund_events_apply_verified_provider_status(
    refund_webhook_records,
    monkeypatch,
    event_type,
    provider_status,
    expected,
):
    records = refund_webhook_records
    FakeRazorpayService.refund_status = provider_status
    response = _post(records, monkeypatch, _payload(records, event_type))

    assert response.status_code == 200, response.text
    assert response.json()["status"] == PaymentWebhookEventStatus.PROCESSED
    refund_status, _, events = _refund_and_events(records)
    assert refund_status == expected
    assert events[0].provider_refund_id == records["provider_refund_id"]


def test_invalid_refund_signature_is_rejected_without_persisting_event(
    refund_webhook_records, monkeypatch
):
    records = refund_webhook_records
    response = _post(
        records,
        monkeypatch,
        _payload(records),
        signature="invalid-signature",
    )

    assert response.status_code == 400
    assert _refund_and_events(records)[2] == []


def test_duplicate_refund_event_id_does_not_repeat_provider_lookup(
    refund_webhook_records, monkeypatch
):
    records = refund_webhook_records
    FakeRazorpayService.fetch_refund_calls = 0
    event_id = f"evt_{uuid4().hex}"
    first = _post(records, monkeypatch, _payload(records), event_id=event_id)
    lookups_after_first = FakeRazorpayService.fetch_refund_calls
    second = _post(records, monkeypatch, _payload(records), event_id=event_id)

    assert first.status_code == second.status_code == 200
    assert lookups_after_first == 1
    assert FakeRazorpayService.fetch_refund_calls == 1


def test_different_event_ids_for_same_refund_are_idempotent(
    refund_webhook_records, monkeypatch
):
    records = refund_webhook_records
    first = _post(records, monkeypatch, _payload(records))
    second = _post(
        records,
        monkeypatch,
        _payload(records, "refund.created"),
    )

    assert first.status_code == second.status_code == 200
    refund_status, _, events = _refund_and_events(records)
    assert refund_status == PaymentRefundStatus.PROCESSED
    assert len(events) == 2
    assert all(event.status == PaymentWebhookEventStatus.PROCESSED for event in events)


@pytest.mark.parametrize(
    "changes",
    [
        {"payment_id": "pay_wrong"},
        {"amount": 12499},
        {"currency": "USD"},
    ],
)
def test_mismatched_refund_details_do_not_update_local_record(
    refund_webhook_records, monkeypatch, changes
):
    records = refund_webhook_records
    response = _post(records, monkeypatch, _payload(records, **changes))

    assert response.status_code == 200
    assert response.json()["status"] == PaymentWebhookEventStatus.FAILED
    status, _, events = _refund_and_events(records)
    assert status == PaymentRefundStatus.PROCESSING
    assert events[0].status == PaymentWebhookEventStatus.FAILED


def test_mismatched_provider_order_is_rejected(refund_webhook_records, monkeypatch):
    records = refund_webhook_records
    payload = _payload(records)
    payload["payload"]["payment"]["entity"]["order_id"] = "order_wrong"

    response = _post(records, monkeypatch, payload)

    assert response.status_code == 200
    assert response.json()["status"] == PaymentWebhookEventStatus.FAILED
    assert _refund_and_events(records)[0] == PaymentRefundStatus.PROCESSING


def test_webhook_does_not_guess_local_intent_when_provider_id_was_not_persisted(
    refund_webhook_records, monkeypatch
):
    records = refund_webhook_records
    db = SessionLocal()
    refund = db.get(Refund, records["refund_id"])
    refund.razorpay_refund_id = None
    db.commit()
    db.close()

    response = _post(records, monkeypatch, _payload(records))

    assert response.status_code == 200
    assert response.json()["status"] == PaymentWebhookEventStatus.FAILED
    db = SessionLocal()
    refund = db.get(Refund, records["refund_id"])
    db.close()
    assert refund.status == PaymentRefundStatus.PROCESSING
    assert refund.razorpay_refund_id is None


def test_out_of_order_events_use_current_provider_state(
    refund_webhook_records, monkeypatch
):
    records = refund_webhook_records
    FakeRazorpayService.refund_status = "processed"
    created = _post(
        records,
        monkeypatch,
        _payload(records, "refund.created"),
    )
    failed = _post(
        records,
        monkeypatch,
        _payload(records, "refund.failed"),
    )

    assert created.status_code == failed.status_code == 200
    assert _refund_and_events(records)[0] == PaymentRefundStatus.PROCESSED


def test_terminal_refund_state_is_not_overwritten_by_conflicting_provider_state(
    refund_webhook_records, monkeypatch
):
    records = refund_webhook_records
    db = SessionLocal()
    refund = db.get(Refund, records["refund_id"])
    refund.status = PaymentRefundStatus.FAILED
    db.commit()
    db.close()
    FakeRazorpayService.refund_status = "processed"

    response = _post(records, monkeypatch, _payload(records))

    assert response.status_code == 200
    assert response.json()["status"] == PaymentWebhookEventStatus.FAILED
    assert _refund_and_events(records)[0] == PaymentRefundStatus.FAILED


def test_provider_lookup_failure_is_retryable(refund_webhook_records, monkeypatch):
    records = refund_webhook_records
    FakeRazorpayService.refund_lookup_error = True
    event_id = f"evt_{uuid4().hex}"
    first = _post(records, monkeypatch, _payload(records), event_id=event_id)
    assert first.status_code == 503
    assert (
        _refund_and_events(records)[2][0].status == PaymentWebhookEventStatus.RETRYABLE
    )

    FakeRazorpayService.refund_lookup_error = False
    second = _post(records, monkeypatch, _payload(records), event_id=event_id)

    assert second.status_code == 200
    assert _refund_and_events(records)[0] == PaymentRefundStatus.PROCESSED


def test_payment_lookup_failure_is_retryable(refund_webhook_records, monkeypatch):
    records = refund_webhook_records
    FakeRazorpayService.payment_lookup_error = True

    response = _post(records, monkeypatch, _payload(records))

    assert response.status_code == 503
    assert (
        _refund_and_events(records)[2][0].status == PaymentWebhookEventStatus.RETRYABLE
    )


def test_reconcile_processing_refund_fetches_provider_details(refund_webhook_records):
    records = refund_webhook_records
    db = SessionLocal()
    try:
        refund = reconcile_processing_refund(
            db, records["refund_id"], razorpay_service=FakeRazorpayService()
        )
        assert refund.status == PaymentRefundStatus.PROCESSED
    finally:
        db.close()


def test_reconcile_without_provider_refund_id_stays_unresolved(
    refund_webhook_records,
):
    records = refund_webhook_records
    db = SessionLocal()
    refund = db.get(Refund, records["refund_id"])
    refund.razorpay_refund_id = None
    db.commit()

    with pytest.raises(RefundValidationError, match="manual investigation"):
        reconcile_processing_refund(
            db, records["refund_id"], razorpay_service=FakeRazorpayService()
        )

    assert db.get(Refund, records["refund_id"]).status == PaymentRefundStatus.PROCESSING
    assert db.get(Refund, records["refund_id"]).razorpay_refund_id is None
    assert FakeRazorpayService.fetch_payment_calls == 0
    assert FakeRazorpayService.fetch_refund_calls == 0
    assert FakeRazorpayService.fetch_payment_refunds_calls == 0
    db.close()


def test_reconcile_provider_lookup_failure_does_not_change_refund_state(
    refund_webhook_records,
):
    records = refund_webhook_records
    FakeRazorpayService.refund_lookup_error = True
    db = SessionLocal()
    with pytest.raises(RazorpayIntegrationError):
        reconcile_processing_refund(
            db, records["refund_id"], razorpay_service=FakeRazorpayService()
        )
    db.rollback()
    assert db.get(Refund, records["refund_id"]).status == PaymentRefundStatus.PROCESSING
    db.close()


def test_concurrent_admin_reconciliation_and_webhook_preserve_verified_state(
    refund_webhook_records,
):
    records = refund_webhook_records
    barrier = Barrier(2)
    event_id = f"evt_concurrent_{uuid4().hex}"
    records["event_ids"].append(event_id)
    payload = _payload(records)

    def reconcile():
        barrier.wait()
        db = SessionLocal()
        try:
            return reconcile_processing_refund(
                db,
                records["refund_id"],
                razorpay_service=FakeRazorpayService(),
            ).status
        finally:
            db.close()

    def process_webhook():
        barrier.wait()
        db = SessionLocal()
        try:
            return process_payment_webhook(
                db,
                event_id,
                "refund.processed",
                payload,
                razorpay_service=FakeRazorpayService(),
            )
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        reconcile_future = executor.submit(reconcile)
        webhook_future = executor.submit(process_webhook)
        assert reconcile_future.result(timeout=10) == PaymentRefundStatus.PROCESSED
        assert webhook_future.result(timeout=10) == PaymentWebhookEventStatus.PROCESSED

    assert _refund_and_events(records)[0] == PaymentRefundStatus.PROCESSED
