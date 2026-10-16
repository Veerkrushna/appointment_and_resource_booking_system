from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.api.routes.admin import router as admin_router
from app.core.security import create_access_token
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
from app.schemas.payment_reconciliation import RefundReconciliationReason
from app.services.payment_reconciliation import (
    list_refund_reconciliation_candidates,
)
from app.services.razorpay import RazorpayIntegrationError

client = TestClient(app)


class FakeRefundLookup:
    def __init__(self):
        self.payment_calls = []
        self.refund_calls = []
        self.payment_evidence = {}
        self.refund_evidence = {}
        self.error = None

    def fetch_payment(self, payment_id):
        self.payment_calls.append(payment_id)
        if self.error:
            raise self.error
        return {
            "id": payment_id,
            "order_id": "expected-order",
            "status": "captured",
            "amount": 2500,
            "amount_refunded": 2500,
            "currency": "INR",
            **self.payment_evidence,
        }

    def fetch_refund(self, payment_id, refund_id):
        self.refund_calls.append((payment_id, refund_id))
        if self.error:
            raise self.error
        return {
            "id": refund_id,
            "payment_id": payment_id,
            "amount": 2500,
            "currency": "INR",
            "status": "processed",
            **self.refund_evidence,
        }


def _reconcile_refund_request(records, refund_id, *, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else None
    return client.post(
        f"/api/admin/payment-reconciliation/refunds/{refund_id}/reconcile",
        headers=headers,
    )


@pytest.fixture
def refund_records():
    db = SessionLocal()
    suffix = uuid4().hex
    customer = User(
        name="Refund Reconciliation Customer",
        email=f"refund-reconciliation-{suffix}@example.com",
        password_hash="test",
        role=UserRole.CUSTOMER,
    )
    admin = User(
        name="Refund Reconciliation Admin",
        email=f"refund-reconciliation-admin-{suffix}@example.com",
        password_hash="test",
        role=UserRole.ADMIN,
    )
    provider_user = User(
        name="Refund Reconciliation Provider",
        email=f"refund-reconciliation-provider-{suffix}@example.com",
        password_hash="test",
        role=UserRole.PROVIDER,
    )
    db.add_all([customer, admin, provider_user])
    db.flush()
    records = {
        "db": db,
        "customer_id": customer.id,
        "admin_id": admin.id,
        "provider_id": provider_user.id,
        "payment_ids": [],
        "refund_ids": [],
        "event_ids": [],
    }

    def add_payment(*, provider=PaymentProvider.RAZORPAY, payment_id=None):
        payment = Payment(
            customer_id=customer.id,
            amount=2500,
            currency="INR",
            status=PaymentStatus.CAPTURED,
            provider=provider,
            provider_order_id=f"order_{uuid4().hex}",
            provider_payment_id=f"pay_{uuid4().hex}",
        )
        if payment_id is not None:
            payment.id = payment_id
        db.add(payment)
        db.flush()
        records["payment_ids"].append(payment.id)
        return payment

    def add_refund(
        payment,
        *,
        status,
        amount=2500,
        currency="INR",
        razorpay_refund_id=None,
    ):
        refund = Refund(
            payment_id=payment.id,
            amount=amount,
            currency=currency,
            status=status,
            razorpay_refund_id=razorpay_refund_id,
            idempotency_key=f"refund_{uuid4().hex}",
            reason="reconciliation test",
        )
        db.add(refund)
        db.flush()
        records["refund_ids"].append(refund.id)
        return refund

    records["add_payment"] = add_payment
    records["add_refund"] = add_refund
    db.commit()
    try:
        yield records
    finally:
        db.close()
        cleanup = SessionLocal()
        cleanup.execute(
            delete(PaymentWebhookEvent).where(
                PaymentWebhookEvent.provider_event_id.in_(records["event_ids"])
            )
        )
        cleanup.execute(delete(Refund).where(Refund.id.in_(records["refund_ids"])))
        cleanup.execute(delete(Payment).where(Payment.id.in_(records["payment_ids"])))
        cleanup.execute(
            delete(User).where(
                User.id.in_(
                    [
                        records["customer_id"],
                        records["admin_id"],
                        records["provider_id"],
                    ]
                )
            )
        )
        cleanup.commit()
        cleanup.close()


def test_refund_candidates_include_unresolved_and_missing_provider_id(refund_records):
    db = refund_records["db"]
    payment = refund_records["add_payment"]()
    pending = refund_records["add_refund"](payment, status=PaymentRefundStatus.PENDING)
    processing = refund_records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
        razorpay_refund_id="rfnd_pending",
    )
    db.commit()

    candidates = list_refund_reconciliation_candidates(db)

    by_id = {candidate.refund_id: candidate for candidate in candidates}
    assert set(by_id) == {pending.id, processing.id}
    assert (
        RefundReconciliationReason.REFUND_PENDING
        in by_id[pending.id].investigation_reasons
    )
    assert (
        RefundReconciliationReason.MISSING_PROVIDER_REFUND_ID
        in by_id[pending.id].investigation_reasons
    )
    assert (
        RefundReconciliationReason.REFUND_PROCESSING
        in by_id[processing.id].investigation_reasons
    )
    assert by_id[pending.id].provider_payment_id == payment.provider_payment_id
    assert by_id[pending.id].provider_order_id == payment.provider_order_id


def test_healthy_terminal_refunds_are_not_candidates(refund_records):
    db = refund_records["db"]
    payment = refund_records["add_payment"]()
    processed = refund_records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSED,
        razorpay_refund_id="rfnd_processed",
    )
    failed = refund_records["add_refund"](
        payment,
        status=PaymentRefundStatus.FAILED,
    )
    db.commit()

    candidates = list_refund_reconciliation_candidates(db)

    assert processed.id not in {candidate.refund_id for candidate in candidates}
    assert failed.id not in {candidate.refund_id for candidate in candidates}


def test_refund_amount_currency_and_webhook_identifier_mismatches_are_flagged(
    refund_records,
):
    db = refund_records["db"]
    payment = refund_records["add_payment"]()
    refund = refund_records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSED,
        amount=2600,
        currency="USD",
        razorpay_refund_id=f"rfnd_{uuid4().hex}",
    )
    event_id = f"evt_{uuid4().hex}"
    event = PaymentWebhookEvent(
        provider_event_id=event_id,
        event_type="refund.processed",
        provider_refund_id=refund.razorpay_refund_id,
        provider_payment_id=f"pay_mismatch_{uuid4().hex}",
        provider_order_id=f"order_mismatch_{uuid4().hex}",
        status=PaymentWebhookEventStatus.PROCESSED,
    )
    db.add(event)
    refund_records["event_ids"].append(event_id)
    db.commit()

    candidate = next(
        item
        for item in list_refund_reconciliation_candidates(db)
        if item.refund_id == refund.id
    )

    assert (
        RefundReconciliationReason.INVALID_REFUND_AMOUNT
        in candidate.investigation_reasons
    )
    assert (
        RefundReconciliationReason.REFUND_CURRENCY_MISMATCH
        in candidate.investigation_reasons
    )
    assert (
        RefundReconciliationReason.MISMATCHED_WEBHOOK_PAYMENT_ID
        in candidate.investigation_reasons
    )
    assert (
        RefundReconciliationReason.MISMATCHED_WEBHOOK_ORDER_ID
        in candidate.investigation_reasons
    )


def test_refund_reservations_exceeding_payment_are_flagged(refund_records):
    db = refund_records["db"]
    payment = refund_records["add_payment"]()
    first = refund_records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSED,
        amount=1500,
        razorpay_refund_id=f"rfnd_{uuid4().hex}",
    )
    second = refund_records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
        amount=1500,
        razorpay_refund_id=f"rfnd_{uuid4().hex}",
    )
    db.commit()

    candidates = {
        candidate.refund_id: candidate
        for candidate in list_refund_reconciliation_candidates(db)
    }

    assert first.id in candidates
    assert second.id in candidates
    assert all(
        RefundReconciliationReason.REFUND_RESERVATIONS_EXCEED_PAYMENT
        in candidates[refund_id].investigation_reasons
        for refund_id in (first.id, second.id)
    )


def test_refund_candidate_limit_and_response_shape(refund_records):
    db = refund_records["db"]
    payment = refund_records["add_payment"]()
    refund_records["add_refund"](payment, status=PaymentRefundStatus.PENDING)
    refund_records["add_refund"](payment, status=PaymentRefundStatus.PROCESSING)
    db.commit()

    candidates = list_refund_reconciliation_candidates(db, limit=1)

    assert len(candidates) == 1
    assert set(candidates[0].model_dump()) == {
        "refund_id",
        "status",
        "amount",
        "currency",
        "razorpay_refund_id",
        "refund_reason",
        "payment_id",
        "provider_payment_id",
        "provider_order_id",
        "created_at",
        "updated_at",
        "investigation_reasons",
    }

    with pytest.raises(ValueError, match="limit must be between"):
        list_refund_reconciliation_candidates(db, limit=501)


def test_refund_reconciliation_route_requires_admin_and_returns_candidates(
    refund_records,
):
    db = refund_records["db"]
    payment = refund_records["add_payment"]()
    refund = refund_records["add_refund"](
        payment, status=PaymentRefundStatus.PROCESSING
    )
    db.commit()
    admin_token = create_access_token(refund_records["admin_id"], UserRole.ADMIN)
    provider_token = create_access_token(
        refund_records["provider_id"], UserRole.PROVIDER
    )

    response = client.get(
        "/api/admin/payment-reconciliation/refunds?limit=10",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    item = next(row for row in response.json() if row["refund_id"] == str(refund.id))
    assert item["status"] == PaymentRefundStatus.PROCESSING.value
    assert item["payment_id"] == str(payment.id)

    unauthenticated = client.get("/api/admin/payment-reconciliation/refunds")
    assert unauthenticated.status_code == 401
    non_admin = client.get(
        "/api/admin/payment-reconciliation/refunds",
        headers={"Authorization": f"Bearer {provider_token}"},
    )
    assert non_admin.status_code == 403
    invalid_limit = client.get(
        "/api/admin/payment-reconciliation/refunds?limit=501",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert invalid_limit.status_code == 422


def test_existing_payment_reconciliation_endpoint_contract_is_unchanged():
    from app.schemas.payment_reconciliation import PaymentReconciliationCandidate

    path = "/api/admin/payment-reconciliation"
    assert "get" in app.openapi()["paths"][path]
    route = next(
        route for route in admin_router.routes if getattr(route, "path", None) == path
    )
    assert route.response_model == list[PaymentReconciliationCandidate]
    assert {parameter.name for parameter in route.dependant.query_params} == {
        "stale_created_before",
        "limit",
    }
    assert route.path == path


def test_refund_reconciliation_route_requires_admin(refund_records):
    records = refund_records
    payment = records["add_payment"]()
    refund = records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
        razorpay_refund_id="rfnd_admin_auth",
    )
    records["db"].commit()
    provider_token = create_access_token(records["provider_id"], UserRole.PROVIDER)

    unauthenticated = _reconcile_refund_request(records, refund.id)
    forbidden = _reconcile_refund_request(records, refund.id, token=provider_token)

    assert unauthenticated.status_code == 401
    assert forbidden.status_code == 403


def test_admin_reconciliation_updates_from_verified_provider_evidence(
    refund_records, monkeypatch, caplog
):
    records = refund_records
    payment = records["add_payment"]()
    refund = records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
        razorpay_refund_id="rfnd_verified",
    )
    records["db"].commit()
    provider = FakeRefundLookup()
    provider.payment_evidence = {"order_id": payment.provider_order_id}
    monkeypatch.setattr(
        "app.services.payment_refunds.RazorpayService", lambda: provider
    )
    admin_token = create_access_token(records["admin_id"], UserRole.ADMIN)

    with caplog.at_level("INFO", logger="app.services.payment_refunds"):
        response = _reconcile_refund_request(records, refund.id, token=admin_token)

    assert response.status_code == 200
    assert response.json() == {
        "refund_id": str(refund.id),
        "previous_status": PaymentRefundStatus.PROCESSING.value,
        "status": PaymentRefundStatus.PROCESSED.value,
        "outcome": "updated",
    }
    assert provider.payment_calls == [payment.provider_payment_id]
    assert provider.refund_calls == [
        (payment.provider_payment_id, refund.razorpay_refund_id)
    ]
    assert str(records["admin_id"]) in caplog.text
    assert str(refund.id) in caplog.text
    assert "previous_status=PROCESSING" in caplog.text
    assert "resulting_status=PROCESSED" in caplog.text
    assert "outcome=updated" in caplog.text
    assert "secret" not in caplog.text.lower()


@pytest.mark.parametrize(
    ("local_status", "provider_status"),
    [
        (PaymentRefundStatus.PROCESSED, "processed"),
        (PaymentRefundStatus.FAILED, "failed"),
    ],
)
def test_matching_terminal_refund_state_is_verified_and_unchanged(
    refund_records, monkeypatch, local_status, provider_status
):
    records = refund_records
    payment = records["add_payment"]()
    refund = records["add_refund"](
        payment,
        status=local_status,
        razorpay_refund_id="rfnd_terminal_match",
    )
    records["db"].commit()
    provider = FakeRefundLookup()
    provider.payment_evidence = {"order_id": payment.provider_order_id}
    provider.refund_evidence = {"status": provider_status}
    monkeypatch.setattr(
        "app.services.payment_refunds.RazorpayService", lambda: provider
    )
    admin_token = create_access_token(records["admin_id"], UserRole.ADMIN)

    response = _reconcile_refund_request(records, refund.id, token=admin_token)

    assert response.status_code == 200
    assert response.json()["outcome"] == "unchanged"
    assert response.json()["status"] == local_status.value
    assert provider.payment_calls == [payment.provider_payment_id]
    assert len(provider.refund_calls) == 1


def test_conflicting_terminal_refund_state_is_not_overwritten(
    refund_records, monkeypatch
):
    records = refund_records
    payment = records["add_payment"]()
    refund = records["add_refund"](
        payment,
        status=PaymentRefundStatus.FAILED,
        razorpay_refund_id="rfnd_terminal_conflict",
    )
    records["db"].commit()
    provider = FakeRefundLookup()
    provider.payment_evidence = {"order_id": payment.provider_order_id}
    monkeypatch.setattr(
        "app.services.payment_refunds.RazorpayService", lambda: provider
    )
    admin_token = create_access_token(records["admin_id"], UserRole.ADMIN)

    response = _reconcile_refund_request(records, refund.id, token=admin_token)

    assert response.status_code == 409
    assert "conflicts with a terminal local state" in response.json()["detail"]
    records["db"].refresh(refund)
    assert refund.status == PaymentRefundStatus.FAILED


@pytest.mark.parametrize(
    ("missing_identifier", "expected_status"),
    [
        ("refund", PaymentRefundStatus.PROCESSING),
        ("provider_payment", PaymentRefundStatus.PROCESSING),
        ("provider_order", PaymentRefundStatus.PROCESSING),
    ],
)
def test_missing_identifiers_are_not_guessed_or_looked_up(
    refund_records, monkeypatch, missing_identifier, expected_status
):
    records = refund_records
    payment = records["add_payment"]()
    refund = records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
        razorpay_refund_id="rfnd_missing",
    )
    if missing_identifier == "refund":
        refund.razorpay_refund_id = None
    elif missing_identifier == "provider_payment":
        payment.provider_payment_id = None
    else:
        payment.provider_order_id = None
    records["db"].commit()
    provider = FakeRefundLookup()
    monkeypatch.setattr(
        "app.services.payment_refunds.RazorpayService", lambda: provider
    )
    admin_token = create_access_token(records["admin_id"], UserRole.ADMIN)

    response = _reconcile_refund_request(records, refund.id, token=admin_token)

    assert response.status_code == 409
    assert provider.payment_calls == []
    assert provider.refund_calls == []
    assert expected_status == refund.status


@pytest.mark.parametrize(
    ("payment_evidence", "refund_evidence"),
    [
        ({"id": "pay_wrong"}, {}),
        ({"order_id": "order_wrong"}, {}),
        ({}, {"id": "rfnd_wrong"}),
        ({}, {"payment_id": "pay_wrong"}),
        ({}, {"amount": 2499}),
        ({}, {"currency": "USD"}),
        ({}, {"status": "unknown"}),
        ({"amount_refunded": 2499}, {}),
    ],
)
def test_mismatched_or_unresolved_provider_evidence_does_not_mutate(
    refund_records, monkeypatch, payment_evidence, refund_evidence
):
    records = refund_records
    payment = records["add_payment"]()
    refund = records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
        razorpay_refund_id="rfnd_evidence",
    )
    records["db"].commit()
    provider = FakeRefundLookup()
    provider.payment_evidence = {
        "order_id": payment.provider_order_id,
        **payment_evidence,
    }
    provider.refund_evidence = refund_evidence
    monkeypatch.setattr(
        "app.services.payment_refunds.RazorpayService", lambda: provider
    )
    admin_token = create_access_token(records["admin_id"], UserRole.ADMIN)

    response = _reconcile_refund_request(records, refund.id, token=admin_token)

    assert response.status_code == 502
    records["db"].refresh(refund)
    assert refund.status == PaymentRefundStatus.PROCESSING


@pytest.mark.parametrize(
    ("provider_status", "expected_detail"),
    [
        ("lookup_failure", "Razorpay could not verify this refund"),
        ("unknown", "Razorpay could not verify this refund"),
    ],
)
def test_provider_lookup_failures_are_safe_and_leave_state_unchanged(
    refund_records, monkeypatch, provider_status, expected_detail, caplog
):
    records = refund_records
    payment = records["add_payment"]()
    refund = records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
        razorpay_refund_id="rfnd_provider_failure",
    )
    records["db"].commit()
    provider = FakeRefundLookup()
    provider.payment_evidence = {"order_id": payment.provider_order_id}
    if provider_status == "lookup_failure":
        provider.error = RazorpayIntegrationError("sensitive-provider-response")
    else:
        provider.refund_evidence = {"status": "unrecognized"}
    monkeypatch.setattr(
        "app.services.payment_refunds.RazorpayService", lambda: provider
    )
    admin_token = create_access_token(records["admin_id"], UserRole.ADMIN)

    with caplog.at_level("INFO", logger="app.services.payment_refunds"):
        response = _reconcile_refund_request(records, refund.id, token=admin_token)

    assert response.status_code == 502
    assert expected_detail in response.json()["detail"]
    assert "sensitive-provider-response" not in response.text
    assert "sensitive-provider-response" not in caplog.text
    records["db"].refresh(refund)
    assert refund.status == PaymentRefundStatus.PROCESSING
    assert "outcome=provider_lookup_failed" in caplog.text or (
        "outcome=unverified_provider_evidence" in caplog.text
    )
