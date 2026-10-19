from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

import app.models  # noqa: F401
from app.db.database import SessionLocal
from app.models.payment import Payment, PaymentProvider, PaymentStatus
from app.models.refund import PaymentRefundStatus, Refund
from app.models.user import User, UserRole
from app.services.payment_refunds import (
    RefundConflictError,
    RefundOutcomeUnknownError,
    RefundValidationError,
    create_full_refund,
)
from app.services.razorpay import (
    RazorpayIntegrationError,
    RazorpayRefundOutcomeUnknownError,
    RazorpayRefundRejectedError,
)


@pytest.fixture
def refund_payment():
    token = uuid4()
    db = SessionLocal()
    customer = User(
        name=f"Refund Test {token}",
        email=f"refund-{token}@example.com",
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
    db.commit()
    payment_id = payment.id
    customer_id = customer.id
    provider_payment_id = payment.provider_payment_id
    provider_order_id = payment.provider_order_id
    db.close()

    try:
        yield {
            "payment_id": payment_id,
            "provider_payment_id": provider_payment_id,
            "provider_order_id": provider_order_id,
            "token": token,
        }
    finally:
        cleanup = SessionLocal()
        cleanup.execute(delete(Refund).where(Refund.payment_id == payment_id))
        cleanup.execute(delete(Payment).where(Payment.id == payment_id))
        cleanup.execute(delete(User).where(User.id == customer_id))
        cleanup.commit()
        cleanup.close()


class FakeRazorpayService:
    def __init__(self, records, *, evidence_changes=None, result_changes=None):
        self.records = records
        self.evidence_changes = evidence_changes or {}
        self.result_changes = result_changes or {}
        self.fetch_calls = []
        self.refund_calls = []
        self.refund_error = None
        self.on_refund = None

    def fetch_payment(self, payment_id):
        self.fetch_calls.append(payment_id)
        return {
            "id": self.records["provider_payment_id"],
            "order_id": self.records["provider_order_id"],
            "status": "captured",
            "amount": 12500,
            "amount_refunded": 0,
            "currency": "INR",
            **self.evidence_changes,
        }

    def create_full_refund(self, payment_id, amount, idempotency_key):
        self.refund_calls.append((payment_id, amount, idempotency_key))
        if self.on_refund is not None:
            self.on_refund()
        if self.refund_error is not None:
            raise self.refund_error
        return {
            "id": f"rfnd_{uuid4().hex}",
            "payment_id": payment_id,
            "amount": amount,
            "currency": "INR",
            "status": "processed",
            **self.result_changes,
        }


def _run_refund(records, provider, *, idempotency_key=None):
    db = SessionLocal()
    try:
        refund = create_full_refund(
            db,
            records["payment_id"],
            idempotency_key or f"refund-{records['token']}",
            "Appointment cancelled",
            razorpay_service=provider,
        )
        db.expunge(refund)
        return SimpleNamespace(
            id=refund.id,
            payment_id=refund.payment_id,
            amount=refund.amount,
            currency=refund.currency,
            status=refund.status,
            razorpay_refund_id=refund.razorpay_refund_id,
        )
    finally:
        db.close()


def test_create_full_refund_verifies_and_persists_provider_result(
    refund_payment, caplog
):
    caplog.set_level("INFO")
    provider = FakeRazorpayService(refund_payment)

    refund = _run_refund(refund_payment, provider)

    assert refund.payment_id == refund_payment["payment_id"]
    assert refund.amount == 12500
    assert refund.currency == "INR"
    assert refund.status == PaymentRefundStatus.PROCESSED
    assert refund.razorpay_refund_id.startswith("rfnd_")
    assert provider.fetch_calls == [refund_payment["provider_payment_id"]]
    assert provider.refund_calls == [
        (
            refund_payment["provider_payment_id"],
            12500,
            f"refund-{refund_payment['token']}",
        )
    ]
    response_log = next(
        record
        for record in caplog.records
        if getattr(record, "refund_event", None) == "provider_response_received"
    )
    assert response_log.refund_id == str(refund.id)
    assert response_log.payment_id == str(refund_payment["payment_id"])
    assert response_log.amount == 12500
    assert response_log.currency == "INR"
    assert response_log.provider_response_status == "processed"
    assert response_log.provider_refund_id_returned is True
    persisted_log = next(
        record
        for record in caplog.records
        if getattr(record, "refund_event", None) == "provider_result_persisted"
    )
    assert persisted_log.provider_refund_id_returned is True

    db = SessionLocal()
    payment = db.get(Payment, refund_payment["payment_id"])
    assert payment.status == PaymentStatus.CAPTURED
    db.close()


@pytest.mark.parametrize(
    ("provider_status", "expected_status"),
    [
        ("pending", PaymentRefundStatus.PROCESSING),
        ("failed", PaymentRefundStatus.FAILED),
    ],
)
def test_provider_refund_status_is_persisted(
    refund_payment, provider_status, expected_status
):
    provider = FakeRazorpayService(
        refund_payment, result_changes={"status": provider_status}
    )

    refund = _run_refund(refund_payment, provider)

    assert refund.status == expected_status
    assert refund.razorpay_refund_id.startswith("rfnd_")


@pytest.mark.parametrize(
    "evidence_changes",
    [
        {"status": "authorized"},
        {"order_id": "order_different"},
        {"amount": 12499},
        {"currency": "USD"},
        {"id": "pay_different"},
    ],
)
def test_invalid_provider_payment_evidence_prevents_refund(
    refund_payment, evidence_changes
):
    provider = FakeRazorpayService(refund_payment, evidence_changes=evidence_changes)

    with pytest.raises(RefundValidationError):
        _run_refund(refund_payment, provider)

    assert provider.refund_calls == []
    db = SessionLocal()
    assert (
        db.scalar(
            select(Refund).where(Refund.payment_id == refund_payment["payment_id"])
        )
        is None
    )
    db.close()


def test_existing_provider_refund_blocks_full_refund(refund_payment):
    provider = FakeRazorpayService(
        refund_payment, evidence_changes={"amount_refunded": 1}
    )

    with pytest.raises(RefundConflictError):
        _run_refund(refund_payment, provider)

    assert provider.refund_calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [("provider_payment_id", None), ("provider_order_id", None)],
)
def test_missing_provider_identifiers_prevent_refund(refund_payment, field, value):
    db = SessionLocal()
    payment = db.get(Payment, refund_payment["payment_id"])
    setattr(payment, field, value)
    db.commit()
    db.close()

    provider = FakeRazorpayService(refund_payment)
    with pytest.raises(RefundValidationError):
        _run_refund(refund_payment, provider)
    assert provider.fetch_calls == []
    assert provider.refund_calls == []


def test_local_captured_status_is_not_capture_evidence(refund_payment):
    db = SessionLocal()
    payment = db.get(Payment, refund_payment["payment_id"])
    payment.status = PaymentStatus.CREATED
    db.commit()
    db.close()

    provider = FakeRazorpayService(refund_payment)
    with pytest.raises(RefundValidationError):
        _run_refund(refund_payment, provider)
    assert provider.fetch_calls == []
    assert provider.refund_calls == []


def test_duplicate_request_returns_existing_refund_without_second_provider_call(
    refund_payment,
):
    provider = FakeRazorpayService(refund_payment)
    idempotency_key = f"duplicate-{refund_payment['token']}"

    first = _run_refund(refund_payment, provider, idempotency_key=idempotency_key)
    second = _run_refund(refund_payment, provider, idempotency_key=idempotency_key)

    assert second.id == first.id
    assert len(provider.refund_calls) == 1


def test_concurrent_refund_reservations_allow_only_one_provider_request(refund_payment):
    provider = FakeRazorpayService(refund_payment)
    provider_entered = Event()
    release_provider = Event()

    def hold_provider_request():
        provider_entered.set()
        assert release_provider.wait(timeout=10)

    provider.on_refund = hold_provider_request

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            _run_refund,
            refund_payment,
            provider,
            idempotency_key=f"concurrent-a-{refund_payment['token']}",
        )
        assert provider_entered.wait(timeout=10)
        second = executor.submit(
            _run_refund,
            refund_payment,
            provider,
            idempotency_key=f"concurrent-b-{refund_payment['token']}",
        )
        with pytest.raises(RefundConflictError):
            second.result(timeout=10)
        release_provider.set()
        result = first.result(timeout=10)

    assert result.status == PaymentRefundStatus.PROCESSED
    assert len(provider.refund_calls) == 1


def test_provider_rejection_is_persisted_as_failed(refund_payment, caplog):
    provider = FakeRazorpayService(refund_payment)
    provider.refund_error = RazorpayRefundRejectedError("rejected")

    with pytest.raises(RazorpayIntegrationError):
        _run_refund(refund_payment, provider)

    db = SessionLocal()
    refund = db.scalar(
        select(Refund).where(Refund.payment_id == refund_payment["payment_id"])
    )
    assert refund.status == PaymentRefundStatus.FAILED
    assert refund.razorpay_refund_id is None
    db.close()
    failure_log = next(
        record
        for record in caplog.records
        if getattr(record, "refund_event", None) == "submission_failed"
    )
    assert failure_log.refund_id
    assert failure_log.payment_id == str(refund_payment["payment_id"])
    assert failure_log.failure_classification == "definitive_rejection"
    assert failure_log.provider_refund_id_returned is False


def test_unclassified_provider_integration_error_does_not_mark_refund_failed(
    refund_payment,
):
    provider = FakeRazorpayService(refund_payment)
    provider.refund_error = RazorpayIntegrationError("provider unavailable")
    idempotency_key = f"integration-failure-{refund_payment['token']}"

    with pytest.raises(RefundOutcomeUnknownError):
        _run_refund(
            refund_payment,
            provider,
            idempotency_key=idempotency_key,
        )

    existing = _run_refund(
        refund_payment,
        provider,
        idempotency_key=idempotency_key,
    )
    assert existing.status == PaymentRefundStatus.PROCESSING
    assert existing.razorpay_refund_id is None
    assert len(provider.refund_calls) == 1


def test_provider_timeout_keeps_reservation_and_duplicate_does_not_resubmit(
    refund_payment, caplog
):
    provider = FakeRazorpayService(refund_payment)
    provider.refund_error = RazorpayRefundOutcomeUnknownError(
        "timeout", failure_classification="timeout"
    )
    idempotency_key = f"uncertain-{refund_payment['token']}"

    with pytest.raises(RefundOutcomeUnknownError):
        _run_refund(refund_payment, provider, idempotency_key=idempotency_key)

    existing = _run_refund(refund_payment, provider, idempotency_key=idempotency_key)
    assert existing.status == PaymentRefundStatus.PROCESSING
    assert existing.razorpay_refund_id is None
    assert len(provider.refund_calls) == 1
    failure_log = next(
        record
        for record in caplog.records
        if getattr(record, "refund_event", None) == "submission_failed"
    )
    assert failure_log.failure_classification == "timeout"


@pytest.mark.parametrize("uncertain_commit", ["intent", "provider_result"])
def test_uncertain_commit_outcome_is_reconciled_without_resubmission(
    refund_payment, uncertain_commit
):
    provider = FakeRazorpayService(refund_payment)
    db = SessionLocal()
    original_commit = db.commit
    commit_count = 0

    def commit_then_raise():
        nonlocal commit_count
        commit_count += 1
        original_commit()
        if (uncertain_commit == "intent" and commit_count == 1) or (
            uncertain_commit == "provider_result" and commit_count == 2
        ):
            raise SQLAlchemyError("simulated lost commit acknowledgement")

    db.commit = commit_then_raise
    try:
        result = create_full_refund(
            db,
            refund_payment["payment_id"],
            f"uncertain-commit-{uncertain_commit}-{refund_payment['token']}",
            "Appointment cancelled",
            razorpay_service=provider,
        )
        result_status = result.status
        result_provider_refund_id = result.razorpay_refund_id
    finally:
        db.close()

    assert result_status == PaymentRefundStatus.PROCESSED
    assert result_provider_refund_id
    assert len(provider.refund_calls) == 1


def test_provider_result_persistence_failure_keeps_intent_and_prevents_resubmission(
    refund_payment, caplog
):
    provider = FakeRazorpayService(refund_payment)
    db = SessionLocal()
    original_commit = db.commit
    commit_count = 0

    def fail_provider_result_commit():
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise SQLAlchemyError("simulated database write failure")
        original_commit()

    db.commit = fail_provider_result_commit
    idempotency_key = f"provider-result-write-failure-{refund_payment['token']}"
    try:
        with pytest.raises(RefundOutcomeUnknownError):
            create_full_refund(
                db,
                refund_payment["payment_id"],
                idempotency_key,
                "Appointment cancelled",
                razorpay_service=provider,
            )
    finally:
        db.close()

    retry = _run_refund(
        refund_payment,
        provider,
        idempotency_key=idempotency_key,
    )

    assert retry.status == PaymentRefundStatus.PROCESSING
    assert retry.razorpay_refund_id is None
    assert len(provider.refund_calls) == 1
    persistence_log = next(
        record
        for record in caplog.records
        if getattr(record, "refund_event", None) == "provider_result_persistence_failed"
    )
    assert persistence_log.refund_id
    assert persistence_log.payment_id == str(refund_payment["payment_id"])
    assert persistence_log.amount == 12500
    assert persistence_log.currency == "INR"
    assert persistence_log.provider_refund_id_returned is True
    assert persistence_log.failure_classification == "database_persistence_failure"


@pytest.mark.parametrize(
    "result_changes",
    [
        {"payment_id": "pay_different"},
        {"amount": 12499},
        {"currency": "USD"},
        {"status": "unknown"},
    ],
)
def test_unverifiable_provider_refund_response_remains_reserved(
    refund_payment, result_changes
):
    provider = FakeRazorpayService(refund_payment, result_changes=result_changes)
    idempotency_key = f"bad-response-{refund_payment['token']}"

    with pytest.raises(RefundOutcomeUnknownError):
        _run_refund(refund_payment, provider, idempotency_key=idempotency_key)

    existing = _run_refund(refund_payment, provider, idempotency_key=idempotency_key)
    assert existing.status == PaymentRefundStatus.PROCESSING
    assert existing.razorpay_refund_id is None
    assert len(provider.refund_calls) == 1
