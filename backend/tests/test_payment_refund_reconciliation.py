from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes.admin import router as admin_router
from app.core.security import create_access_token, get_current_user
from app.db.database import SessionLocal
from app.main import app
from app.models.appointment import Appointment, AppointmentStatus
from app.models.appointment_cancellation import (
    AppointmentCancellation,
)
from app.models.appointment_cancellation import (
    RefundStatus as CancellationRefundStatus,
)
from app.models.payment import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    PaymentWebhookEvent,
    PaymentWebhookEventStatus,
)
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.refund import PaymentRefundStatus, Refund
from app.models.service import Service, ServiceStatus
from app.models.user import User, UserRole
from app.schemas.payment_reconciliation import RefundReconciliationReason
from app.services.payment_reconciliation import (
    list_refund_reconciliation_candidates,
)
from app.services.razorpay import RazorpayIntegrationError, RazorpayLookupError

client = TestClient(app)


class FakeRefundLookup:
    def __init__(self):
        self.calls = []
        self.payment_calls = []
        self.refund_calls = []
        self.payment_refund_calls = []
        self.payment_evidence = {}
        self.refund_evidence = {}
        self.payment_refunds = {"entity": "collection", "count": 0, "items": []}
        self.error = None
        self.refund_history_error = None
        self.refund_error = None

    def fetch_payment(self, payment_id):
        self.calls.append("payment")
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
        self.calls.append("refund")
        self.refund_calls.append((payment_id, refund_id))
        if self.refund_error:
            raise self.refund_error
        if self.refund_evidence is None:
            return None
        return {
            "id": refund_id,
            "payment_id": payment_id,
            "amount": 2500,
            "currency": "INR",
            "status": "processed",
            **self.refund_evidence,
        }

    def fetch_payment_refunds(self, payment_id):
        self.payment_refund_calls.append(payment_id)
        if self.refund_history_error:
            raise self.refund_history_error
        if self.error:
            raise self.error
        return self.payment_refunds

    def create_full_refund(self, *_args, **_kwargs):
        raise AssertionError("Reconciliation must never submit a refund")


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
    provider = Provider(
        name=f"Refund Reconciliation Provider {suffix}",
        type=ProviderType.PERSON,
        email=f"refund-reconciliation-provider-profile-{suffix}@example.com",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    service = Service(
        name=f"Refund Reconciliation Service {suffix}",
        duration_minutes=30,
        category="Testing",
        capacity=1,
        status=ServiceStatus.ACTIVE,
    )
    db.add_all([customer, admin, provider_user, provider, service])
    db.flush()
    appointment_start = datetime.now(UTC) + timedelta(days=30)
    appointment = Appointment(
        service_id=service.id,
        provider_id=provider.id,
        customer_id=customer.id,
        user_name=customer.name,
        user_email=customer.email,
        appointment_start=appointment_start,
        appointment_end=appointment_start + timedelta(minutes=30),
        duration_minutes=30,
        status=AppointmentStatus.CONFIRMED,
    )
    db.add(appointment)
    db.flush()
    records = {
        "db": db,
        "customer_id": customer.id,
        "admin_id": admin.id,
        "provider_id": provider_user.id,
        "appointment_id": appointment.id,
        "service_id": service.id,
        "provider_profile_id": provider.id,
        "payment_ids": [],
        "refund_ids": [],
        "cancellation_ids": [],
        "event_ids": [],
    }

    def add_payment(
        *,
        provider=PaymentProvider.RAZORPAY,
        payment_id=None,
        appointment_id=None,
    ):
        payment = Payment(
            customer_id=customer.id,
            appointment_id=appointment_id,
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

    def add_cancellation(appointment_id):
        cancellation = AppointmentCancellation(
            appointment_id=appointment_id,
            cancelled_by="customer",
            reason="reconciliation test",
            refund_status=CancellationRefundStatus.PENDING,
        )
        db.add(cancellation)
        db.flush()
        records["cancellation_ids"].append(cancellation.id)
        return cancellation

    records["add_cancellation"] = add_cancellation
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
        cleanup.execute(
            delete(AppointmentCancellation).where(
                AppointmentCancellation.id.in_(records["cancellation_ids"])
            )
        )
        cleanup.execute(delete(Payment).where(Payment.id.in_(records["payment_ids"])))
        cleanup.execute(
            delete(Appointment).where(Appointment.id == records["appointment_id"])
        )
        cleanup.execute(delete(Service).where(Service.id == records["service_id"]))
        cleanup.execute(
            delete(Provider).where(Provider.id == records["provider_profile_id"])
        )
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
    payment = refund_records["add_payment"](
        appointment_id=refund_records["appointment_id"]
    )
    pending = refund_records["add_refund"](payment, status=PaymentRefundStatus.PENDING)
    processing = refund_records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
        razorpay_refund_id="rfnd_pending",
    )
    db.commit()

    candidates = list_refund_reconciliation_candidates(db)

    by_id = {candidate.refund_id: candidate for candidate in candidates}
    assert {pending.id, processing.id}.issubset(by_id)
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
    assert by_id[pending.id].appointment_id == refund_records["appointment_id"]
    assert by_id[pending.id].series_id is None


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
        "appointment_id",
        "series_id",
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
    payment = refund_records["add_payment"](
        appointment_id=refund_records["appointment_id"]
    )
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
    assert item["appointment_id"] == str(refund_records["appointment_id"])
    assert item["series_id"] is None

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


def test_refund_candidate_database_error_is_logged_and_returns_safe_503(
    refund_records, monkeypatch, caplog
):
    import logging

    def fail_query(*_args, **_kwargs):
        raise SQLAlchemyError("refund schema is unavailable")

    monkeypatch.setattr(
        "app.api.routes.admin.list_refund_reconciliation_candidates",
        fail_query,
    )
    monkeypatch.setitem(
        app.dependency_overrides,
        get_current_user,
        lambda: refund_records["db"].get(User, refund_records["admin_id"]),
    )

    with caplog.at_level(logging.ERROR, logger="app.api.routes.admin"):
        response = client.get(
            "/api/admin/payment-reconciliation/refunds",
            headers={"Authorization": "******"},
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Refund reconciliation is temporarily unavailable."
    }
    assert "Unable to load admin refund reconciliation candidates" in caplog.text
    assert "refund schema is unavailable" in caplog.text


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
        "failure_classification": None,
        "outcome": "updated",
    }
    assert provider.payment_calls == [payment.provider_payment_id]
    assert provider.calls == ["refund", "payment"]
    assert provider.refund_calls == [
        (payment.provider_payment_id, refund.razorpay_refund_id)
    ]
    assert str(records["admin_id"]) in caplog.text
    assert str(refund.id) in caplog.text
    assert "previous_status=PROCESSING" in caplog.text
    assert "resulting_status=PROCESSED" in caplog.text
    assert "outcome=updated" in caplog.text
    assert "secret" not in caplog.text.lower()


def test_admin_reconciliation_accepts_verified_full_refunded_payment(
    refund_records, monkeypatch
):
    records = refund_records
    appointment_id = records["appointment_id"]
    payment = records["add_payment"](appointment_id=appointment_id)
    refund = records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
        razorpay_refund_id="rfnd_fully_refunded",
    )
    cancellation = records["add_cancellation"](appointment_id)
    records["db"].commit()
    provider = FakeRefundLookup()
    provider.payment_evidence = {
        "id": payment.provider_payment_id,
        "order_id": payment.provider_order_id,
        "status": "refunded",
        "amount": payment.amount,
        "amount_refunded": payment.amount,
        "currency": payment.currency,
    }
    monkeypatch.setattr(
        "app.services.payment_refunds.RazorpayService", lambda: provider
    )
    admin_token = create_access_token(records["admin_id"], UserRole.ADMIN)

    response = _reconcile_refund_request(records, refund.id, token=admin_token)

    assert response.status_code == 200
    assert response.json()["status"] == PaymentRefundStatus.PROCESSED.value
    records["db"].refresh(refund)
    records["db"].refresh(cancellation)
    assert refund.status == PaymentRefundStatus.PROCESSED
    assert cancellation.refund_status == CancellationRefundStatus.REFUNDED


@pytest.mark.parametrize(
    ("provider_status", "expected_local_status", "expected_cancellation_status"),
    [
        (
            "pending",
            PaymentRefundStatus.PROCESSING,
            CancellationRefundStatus.PENDING,
        ),
        (
            "processed",
            PaymentRefundStatus.PROCESSED,
            CancellationRefundStatus.REFUNDED,
        ),
        (
            "failed",
            PaymentRefundStatus.FAILED,
            CancellationRefundStatus.PENDING,
        ),
    ],
)
def test_reconcile_stored_provider_refund_statuses_safely(
    refund_records,
    monkeypatch,
    provider_status,
    expected_local_status,
    expected_cancellation_status,
):
    records = refund_records
    appointment_id = records["appointment_id"]
    payment = records["add_payment"](appointment_id=appointment_id)
    refund = records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
        razorpay_refund_id="rfnd_status_check",
    )
    cancellation = records["add_cancellation"](appointment_id)
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
    assert response.json()["status"] == expected_local_status.value
    assert provider.refund_calls == [
        (payment.provider_payment_id, refund.razorpay_refund_id)
    ]
    assert provider.payment_calls == [payment.provider_payment_id]
    records["db"].refresh(refund)
    records["db"].refresh(cancellation)
    assert refund.status == expected_local_status
    assert cancellation.refund_status == expected_cancellation_status


def test_missing_provider_refund_id_is_recovered_from_unique_matching_evidence(
    refund_records, monkeypatch
):
    records = refund_records
    payment = records["add_payment"]()
    refund = records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
    )
    records["db"].commit()
    provider = FakeRefundLookup()
    provider.payment_evidence = {"order_id": payment.provider_order_id}
    provider.payment_refunds = {
        "entity": "collection",
        "count": 1,
        "items": [
            {
                "id": "rfnd_recovered",
                "payment_id": payment.provider_payment_id,
                "amount": refund.amount,
                "currency": refund.currency,
                "status": "processed",
                "created_at": int(refund.created_at.timestamp()),
            }
        ],
    }
    monkeypatch.setattr(
        "app.services.payment_refunds.RazorpayService", lambda: provider
    )
    admin_token = create_access_token(records["admin_id"], UserRole.ADMIN)

    response = _reconcile_refund_request(records, refund.id, token=admin_token)

    assert response.status_code == 200
    assert response.json()["status"] == PaymentRefundStatus.PROCESSED.value
    records["db"].refresh(refund)
    assert refund.razorpay_refund_id == "rfnd_recovered"
    assert refund.status == PaymentRefundStatus.PROCESSED
    assert provider.payment_refund_calls == [payment.provider_payment_id]
    assert provider.refund_calls == [(payment.provider_payment_id, "rfnd_recovered")]


@pytest.mark.parametrize(
    ("refund_items", "expected_outcome"),
    [
        ([], "no_matching_refund"),
        (
            [
                {
                    "id": "rfnd_before_intent",
                    "payment_id": "expected-payment",
                    "amount": 2500,
                    "currency": "INR",
                    "status": "processed",
                    "created_at": 0,
                }
            ],
            "no_matching_refund",
        ),
        (
            [
                {
                    "id": "rfnd_ambiguous_1",
                    "payment_id": "expected-payment",
                    "amount": 2500,
                    "currency": "INR",
                    "status": "processed",
                    "created_at": 2_000_000_000,
                },
                {
                    "id": "rfnd_ambiguous_2",
                    "payment_id": "expected-payment",
                    "amount": 2500,
                    "currency": "INR",
                    "status": "processed",
                    "created_at": 2_000_000_000,
                },
            ],
            "multiple_matching_refunds",
        ),
    ],
)
def test_unmatched_or_ambiguous_refund_history_preserves_uncertainty(
    refund_records, monkeypatch, refund_items, expected_outcome, caplog
):
    records = refund_records
    payment = records["add_payment"]()
    refund = records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
    )
    records["db"].commit()
    provider = FakeRefundLookup()
    provider.payment_evidence = {"order_id": payment.provider_order_id}
    provider.payment_refunds = {
        "entity": "collection",
        "count": len(refund_items),
        "items": [
            {**item, "payment_id": payment.provider_payment_id} for item in refund_items
        ],
    }
    monkeypatch.setattr(
        "app.services.payment_refunds.RazorpayService", lambda: provider
    )
    admin_token = create_access_token(records["admin_id"], UserRole.ADMIN)

    with caplog.at_level("WARNING", logger="app.services.payment_refunds"):
        response = _reconcile_refund_request(records, refund.id, token=admin_token)

    assert response.status_code == 200
    assert response.json()["outcome"] == expected_outcome
    expected_classification = (
        "provider_refund_ambiguous"
        if expected_outcome == "multiple_matching_refunds"
        else "provider_refund_history_empty"
        if not refund_items
        else "provider_refund_not_found"
    )
    assert response.json()["failure_classification"] == expected_classification
    assert any(
        getattr(record, "failure_classification", None) == expected_classification
        for record in caplog.records
    )
    assert response.json()["status"] == PaymentRefundStatus.PROCESSING.value
    records["db"].refresh(refund)
    assert refund.razorpay_refund_id is None
    assert refund.status == PaymentRefundStatus.PROCESSING
    assert provider.payment_refund_calls == [payment.provider_payment_id]
    assert provider.refund_calls == []


def test_incomplete_refund_history_preserves_uncertainty(refund_records, monkeypatch):
    records = refund_records
    payment = records["add_payment"]()
    refund = records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
    )
    records["db"].commit()
    provider = FakeRefundLookup()
    provider.payment_evidence = {"order_id": payment.provider_order_id}
    provider.payment_refunds = {
        "entity": "collection",
        "count": 2,
        "items": [],
    }
    monkeypatch.setattr(
        "app.services.payment_refunds.RazorpayService", lambda: provider
    )
    admin_token = create_access_token(records["admin_id"], UserRole.ADMIN)

    response = _reconcile_refund_request(records, refund.id, token=admin_token)

    assert response.status_code == 200
    assert response.json()["outcome"] == "evidence_conflict"
    assert (
        response.json()["failure_classification"]
        == "provider_refund_history_invalid"
    )
    records["db"].refresh(refund)
    assert refund.razorpay_refund_id is None
    assert refund.status == PaymentRefundStatus.PROCESSING
    assert provider.refund_calls == []


@pytest.mark.parametrize("failure_stage", ["payment", "history", "refund"])
def test_missing_provider_refund_id_provider_error_preserves_local_state(
    refund_records, monkeypatch, failure_stage
):
    records = refund_records
    payment = records["add_payment"]()
    refund = records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
    )
    records["db"].commit()
    provider = FakeRefundLookup()
    provider.payment_evidence = {"order_id": payment.provider_order_id}
    provider.payment_refunds = {
        "entity": "collection",
        "count": 1,
        "items": [
            {
                "id": "rfnd_lookup_error",
                "payment_id": payment.provider_payment_id,
                "amount": refund.amount,
                "currency": refund.currency,
                "status": "processed",
                "created_at": int(refund.created_at.timestamp()),
            }
        ],
    }
    if failure_stage == "payment":
        provider.error = RazorpayIntegrationError("private provider details")
    elif failure_stage == "history":
        provider.refund_history_error = RazorpayLookupError(
            "Razorpay refund history lookup failed",
            failure_classification="provider_server_error",
            provider_http_status=503,
        )
    else:
        provider.refund_error = RazorpayIntegrationError("private provider details")
    monkeypatch.setattr(
        "app.services.payment_refunds.RazorpayService", lambda: provider
    )
    admin_token = create_access_token(records["admin_id"], UserRole.ADMIN)

    response = _reconcile_refund_request(records, refund.id, token=admin_token)

    assert response.status_code == 200
    assert response.json()["outcome"] == "provider_unavailable"
    assert response.json()["failure_classification"] == (
        "provider_server_error" if failure_stage == "history" else "provider_unavailable"
    )
    records["db"].refresh(refund)
    assert refund.status == PaymentRefundStatus.PROCESSING
    assert refund.razorpay_refund_id is None
    assert provider.refund_calls == (
        [(payment.provider_payment_id, "rfnd_lookup_error")]
        if failure_stage == "refund"
        else []
    )


def test_missing_provider_refund_id_conflicting_direct_evidence_is_not_saved(
    refund_records, monkeypatch
):
    records = refund_records
    payment = records["add_payment"]()
    refund = records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
    )
    records["db"].commit()
    provider = FakeRefundLookup()
    provider.payment_evidence = {"order_id": payment.provider_order_id}
    provider.payment_refunds = {
        "entity": "collection",
        "count": 1,
        "items": [
            {
                "id": "rfnd_evidence_conflict",
                "payment_id": payment.provider_payment_id,
                "amount": refund.amount,
                "currency": refund.currency,
                "status": "processed",
                "created_at": int(refund.created_at.timestamp()),
            }
        ],
    }
    provider.refund_evidence = {"status": "pending"}
    monkeypatch.setattr(
        "app.services.payment_refunds.RazorpayService", lambda: provider
    )
    admin_token = create_access_token(records["admin_id"], UserRole.ADMIN)

    response = _reconcile_refund_request(records, refund.id, token=admin_token)

    assert response.status_code == 200
    assert response.json()["outcome"] == "evidence_conflict"
    records["db"].refresh(refund)
    assert refund.status == PaymentRefundStatus.PROCESSING
    assert refund.razorpay_refund_id is None
    assert provider.refund_calls == [
        (payment.provider_payment_id, "rfnd_evidence_conflict")
    ]


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
    ("missing_identifier", "expected_http_status"),
    [
        ("refund", 200),
        ("provider_payment", 409),
        ("provider_order", 409),
    ],
)
def test_missing_identifiers_only_allow_recovery_when_payment_link_is_valid(
    refund_records, monkeypatch, missing_identifier, expected_http_status
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
    provider.payment_evidence = {"order_id": payment.provider_order_id}
    monkeypatch.setattr(
        "app.services.payment_refunds.RazorpayService", lambda: provider
    )
    admin_token = create_access_token(records["admin_id"], UserRole.ADMIN)

    response = _reconcile_refund_request(records, refund.id, token=admin_token)

    assert response.status_code == expected_http_status
    if missing_identifier == "refund":
        assert response.json()["outcome"] == "no_matching_refund"
        assert provider.payment_calls == [payment.provider_payment_id]
        assert provider.payment_refund_calls == [payment.provider_payment_id]
    else:
        assert provider.payment_calls == []
    assert provider.refund_calls == []
    records["db"].refresh(refund)
    assert refund.status == PaymentRefundStatus.PROCESSING


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
    ("provider_status", "expected_detail", "expected_classification"),
    [
        (
            "lookup_failure",
            "Razorpay refund verification is temporarily unavailable",
            "provider_unavailable",
        ),
        (
            "unknown",
            "Razorpay refund status is not recognized",
            "refund_status_unrecognized",
        ),
    ],
)
def test_provider_lookup_failures_are_safe_and_leave_state_unchanged(
    refund_records,
    monkeypatch,
    provider_status,
    expected_detail,
    expected_classification,
    caplog,
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

    with caplog.at_level("INFO"):
        response = _reconcile_refund_request(records, refund.id, token=admin_token)

    assert response.status_code == 502
    assert expected_detail in response.json()["detail"]
    assert "sensitive-provider-response" not in response.text
    assert "sensitive-provider-response" not in caplog.text
    assert any(
        getattr(record, "failure_classification", None) == expected_classification
        for record in caplog.records
    )
    records["db"].refresh(refund)
    assert refund.status == PaymentRefundStatus.PROCESSING


@pytest.mark.parametrize(
    ("evidence_kind", "evidence", "expected_classification"),
    [
        ("refund", None, "refund_response_shape_invalid"),
        ("refund", {"id": "rfnd_other"}, "provider_refund_id_mismatch"),
        ("refund", {"payment_id": "pay_other"}, "provider_payment_id_mismatch"),
        ("refund", {"amount": 2400}, "refund_amount_mismatch"),
        ("refund", {"currency": "USD"}, "refund_currency_mismatch"),
        ("refund", {"status": None}, "refund_status_invalid"),
        ("refund", {"status": "unknown"}, "refund_status_unrecognized"),
        ("payment", {"id": "pay_other"}, "provider_payment_id_mismatch"),
        ("payment", {"order_id": "order_other"}, "provider_order_id_mismatch"),
        ("payment", {"status": "authorized"}, "provider_payment_not_captured"),
        ("payment", {"amount": 2400}, "payment_amount_mismatch"),
        ("payment", {"currency": "USD"}, "payment_currency_mismatch"),
        (
            "payment",
            {"status": "refunded", "amount_refunded": 2400},
            "payment_refunded_status_total_mismatch",
        ),
        ("payment", {"amount_refunded": 0}, "payment_refunded_total_below_refund"),
    ],
)
def test_admin_reconciliation_logs_precise_evidence_failure_without_mutation(
    refund_records,
    monkeypatch,
    evidence_kind,
    evidence,
    expected_classification,
    caplog,
):
    records = refund_records
    payment = records["add_payment"]()
    refund = records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
        razorpay_refund_id="rfnd_diagnostic",
    )
    records["db"].commit()
    provider = FakeRefundLookup()
    provider.payment_evidence = {"order_id": payment.provider_order_id}
    if evidence_kind == "refund":
        provider.refund_evidence = evidence
    else:
        provider.payment_evidence = {
            "order_id": payment.provider_order_id,
            **evidence,
        }
    monkeypatch.setattr(
        "app.services.payment_refunds.RazorpayService", lambda: provider
    )
    admin_token = create_access_token(records["admin_id"], UserRole.ADMIN)

    with caplog.at_level("WARNING"):
        response = _reconcile_refund_request(records, refund.id, token=admin_token)

    assert response.status_code == 502
    assert "Local refund state was left unchanged." in response.json()["detail"]
    diagnostic = next(
        record
        for record in caplog.records
        if getattr(record, "failure_classification", None) == expected_classification
    )
    assert diagnostic.exception_class == "RefundOutcomeUnknownError"
    assert diagnostic.provider_http_status is None
    assert expected_classification in diagnostic.message
    assert "rfnd_diagnostic" not in caplog.text
    records["db"].refresh(refund)
    assert refund.status == PaymentRefundStatus.PROCESSING
    assert refund.razorpay_refund_id == "rfnd_diagnostic"


def test_missing_provider_refund_returns_sanitized_reason_without_mutation(
    refund_records, monkeypatch, caplog
):
    records = refund_records
    payment = records["add_payment"]()
    refund = records["add_refund"](
        payment,
        status=PaymentRefundStatus.PROCESSING,
        razorpay_refund_id="rfnd_missing_provider",
    )
    records["db"].commit()
    provider = FakeRefundLookup()
    provider.refund_error = RazorpayLookupError(
        "Razorpay did not find the refund for the supplied payment and refund IDs.",
        failure_classification="refund_not_found",
        provider_http_status=404,
    )
    monkeypatch.setattr(
        "app.services.payment_refunds.RazorpayService", lambda: provider
    )
    admin_token = create_access_token(records["admin_id"], UserRole.ADMIN)

    with caplog.at_level("WARNING", logger="app.api.routes.admin"):
        response = _reconcile_refund_request(records, refund.id, token=admin_token)

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Razorpay did not find the refund for the supplied payment and refund IDs. "
        "Local refund state was left unchanged."
    )
    assert any(
        getattr(record, "failure_classification", None) == "refund_not_found"
        for record in caplog.records
    )
    provider_failure = next(
        record
        for record in caplog.records
        if getattr(record, "failure_classification", None) == "refund_not_found"
    )
    assert provider_failure.exception_class == "RazorpayLookupError"
    assert provider_failure.provider_http_status == 404
    records["db"].refresh(refund)
    assert refund.status == PaymentRefundStatus.PROCESSING
    assert refund.razorpay_refund_id == "rfnd_missing_provider"
    assert provider.calls == ["refund"]
