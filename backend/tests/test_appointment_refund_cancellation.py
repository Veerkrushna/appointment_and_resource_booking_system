from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

import app.models  # noqa: F401
from app.core.security import create_access_token
from app.db.database import SessionLocal
from app.main import app
from app.models.appointment import Appointment, AppointmentStatus
from app.models.appointment_cancellation import (
    AppointmentCancellation,
)
from app.models.appointment_cancellation import (
    RefundStatus as CancellationRefundStatus,
)
from app.models.appointment_series import (
    AppointmentSeries,
    AppointmentSeriesEndMode,
    AppointmentSeriesFrequency,
    AppointmentSeriesStatus,
)
from app.models.booking_hold import BookingHold, BookingHoldStatus
from app.models.payment import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    PaymentWebhookEventStatus,
)
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.refund import PaymentRefundStatus, Refund
from app.models.service import Service, ServiceStatus
from app.models.user import User, UserRole
from app.schemas.appointment import AppointmentCancellationCreate
from app.schemas.payment_reconciliation import RefundReconciliationReason
from app.services.booking import (
    CancellationValidationError,
    can_modify_booking,
    cancel_appointment,
)
from app.services.payment_reconciliation import list_refund_reconciliation_candidates
from app.services.payment_refunds import reconcile_processing_refund
from app.services.payment_webhooks import process_payment_webhook
from app.services.razorpay import (
    RazorpayIntegrationError,
    RazorpayRefundOutcomeUnknownError,
    RazorpayRefundRejectedError,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def disable_cancellation_notification(monkeypatch):
    monkeypatch.setattr(
        "app.services.booking.send_cancellation_notification.delay",
        lambda _appointment_id: None,
    )


class FakeRefundProvider:
    def __init__(self, records):
        self.records = records
        self.payment_changes = {}
        self.refund_error = None
        self.payment_error = None
        self.refund_status = "processed"
        self.amount_refunded = 0
        self.refund_calls = []
        self.payment_calls = []

    def fetch_payment(self, payment_id):
        self.payment_calls.append(payment_id)
        if self.payment_error:
            raise self.payment_error
        return {
            "id": self.records["provider_payment_id"],
            "order_id": self.records["provider_order_id"],
            "status": "captured",
            "amount": 12500,
            "amount_refunded": self.amount_refunded,
            "currency": "INR",
            **self.payment_changes,
        }

    def create_full_refund(self, payment_id, amount, idempotency_key):
        self.refund_calls.append((payment_id, amount, idempotency_key))
        if self.refund_error:
            raise self.refund_error
        return {
            "id": f"rfnd_{self.records['token'].hex}",
            "payment_id": payment_id,
            "amount": amount,
            "currency": "INR",
            "status": self.refund_status,
        }

    def fetch_refund(self, payment_id, refund_id):
        return {
            "id": refund_id,
            "payment_id": payment_id,
            "amount": 12500,
            "currency": "INR",
            "status": "processed",
        }


@pytest.fixture
def cancellation_payment():
    token = uuid4()
    db = SessionLocal()
    customer = User(
        name=f"Cancellation Customer {token}",
        email=f"refund-cancel-{token}@example.com",
        password_hash="test",
        role=UserRole.CUSTOMER,
    )
    other_customer = User(
        name=f"Other Customer {token}",
        email=f"refund-cancel-other-{token}@example.com",
        password_hash="test",
        role=UserRole.CUSTOMER,
    )
    provider = Provider(
        name=f"Refund Provider {token}",
        type=ProviderType.PERSON,
        email=f"refund-provider-{token}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    service = Service(
        name=f"Refund Service {token}",
        duration_minutes=30,
        category="Testing",
        capacity=1,
        buffer_time_minutes=0,
        price="125.00",
        status=ServiceStatus.ACTIVE,
    )
    db.add_all([customer, other_customer, provider, service])
    db.flush()
    db.add(ProviderService(provider_id=provider.id, service_id=service.id))
    appointment_start = datetime.now(UTC) + timedelta(days=3)
    appointment_start = appointment_start.replace(
        hour=10, minute=0, second=0, microsecond=0
    )
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
    payment = Payment(
        customer_id=customer.id,
        appointment_id=appointment.id,
        amount=12500,
        currency="INR",
        status=PaymentStatus.CAPTURED,
        provider=PaymentProvider.RAZORPAY,
        provider_order_id=f"order_{token.hex}",
        provider_payment_id=f"pay_{token.hex}",
    )
    db.add(payment)
    db.flush()
    hold = BookingHold(
        customer_id=customer.id,
        service_id=service.id,
        provider_id=provider.id,
        user_name=customer.name,
        user_email=customer.email,
        appointment_start=appointment.appointment_start,
        appointment_end=appointment.appointment_end,
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
        status=BookingHoldStatus.CONVERTED,
        payment_id=payment.id,
    )
    db.add(hold)
    db.commit()
    records = {
        "appointment_id": appointment.id,
        "customer_id": customer.id,
        "other_customer_id": other_customer.id,
        "provider_id": provider.id,
        "service_id": service.id,
        "payment_id": payment.id,
        "hold_id": hold.id,
        "series_ids": [],
        "provider_payment_id": payment.provider_payment_id,
        "provider_order_id": payment.provider_order_id,
        "token": token,
    }
    db.close()

    try:
        yield records
    finally:
        cleanup = SessionLocal()
        cleanup.execute(
            delete(AppointmentCancellation).where(
                AppointmentCancellation.appointment_id == records["appointment_id"]
            )
        )
        cleanup.execute(
            delete(Refund).where(Refund.payment_id == records["payment_id"])
        )
        cleanup.execute(delete(BookingHold).where(BookingHold.id == records["hold_id"]))
        cleanup.execute(delete(Payment).where(Payment.id == records["payment_id"]))
        cleanup.execute(
            delete(Appointment).where(Appointment.id == records["appointment_id"])
        )
        cleanup.execute(
            delete(AppointmentSeries).where(
                AppointmentSeries.id.in_(records["series_ids"])
            )
        )
        cleanup.execute(
            delete(ProviderService).where(
                ProviderService.provider_id == records["provider_id"]
            )
        )
        cleanup.execute(delete(Service).where(Service.id == records["service_id"]))
        cleanup.execute(delete(Provider).where(Provider.id == records["provider_id"]))
        cleanup.execute(
            delete(User).where(
                User.id.in_([records["customer_id"], records["other_customer_id"]])
            )
        )
        cleanup.commit()
        cleanup.close()


def _cancel(records, provider=None, *, customer_id=None):
    db = SessionLocal()
    try:
        cancellation = cancel_appointment(
            db,
            records["appointment_id"],
            AppointmentCancellationCreate(
                cancelled_by="customer",
                reason="Customer cancelled",
            ),
            user_role=UserRole.CUSTOMER,
            customer_id=customer_id or records["customer_id"],
            razorpay_service=provider,
        )
        db.expunge(cancellation)
        return cancellation.id, cancellation.refund_status
    finally:
        db.close()


def test_eligible_cancellation_verifies_payment_then_refunds(cancellation_payment):
    records = cancellation_payment
    provider = FakeRefundProvider(records)

    cancellation_id, cancellation_refund_status = _cancel(records, provider)

    db = SessionLocal()
    appointment = db.get(Appointment, records["appointment_id"])
    payment = db.get(Payment, records["payment_id"])
    refund = db.scalar(select(Refund).where(Refund.payment_id == payment.id))
    cancellation = db.get(AppointmentCancellation, cancellation_id)
    db.close()
    assert appointment.status == AppointmentStatus.CANCELLED
    assert payment.status == PaymentStatus.CAPTURED
    assert provider.payment_calls == [records["provider_payment_id"]]
    assert len(provider.refund_calls) == 1
    assert refund.status == PaymentRefundStatus.PROCESSED
    assert refund.amount == payment.amount
    assert cancellation.refund_status == CancellationRefundStatus.REFUNDED
    assert cancellation_refund_status == CancellationRefundStatus.REFUNDED


@pytest.mark.parametrize(
    ("lead_time", "expected_eligible"),
    [
        (timedelta(hours=2), False),
        (timedelta(hours=2, microseconds=1), True),
    ],
)
@pytest.mark.parametrize(
    "start_offset",
    [timedelta(0), timedelta(hours=5, minutes=30)],
)
def test_refund_eligibility_uses_strict_two_hour_instant_cutoff(
    cancellation_payment,
    monkeypatch,
    lead_time,
    expected_eligible,
    start_offset,
):
    records = cancellation_payment
    frozen_now = datetime(2026, 10, 16, 8, 0, tzinfo=UTC)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen_now if tz is None else frozen_now.astimezone(tz)

    monkeypatch.setattr("app.services.booking.datetime", FrozenDateTime)
    appointment_start = (frozen_now + lead_time).astimezone(timezone(start_offset))
    appointment_end = appointment_start + timedelta(minutes=30)
    db = SessionLocal()
    appointment = db.get(Appointment, records["appointment_id"])
    hold = db.get(BookingHold, records["hold_id"])
    appointment.appointment_start = appointment_start
    appointment.appointment_end = appointment_end
    hold.appointment_start = appointment_start
    hold.appointment_end = appointment_end
    db.commit()
    db.close()

    provider = FakeRefundProvider(records)
    assert can_modify_booking(appointment_start, frozen_now) is expected_eligible

    if expected_eligible:
        _, cancellation_status = _cancel(records, provider)
        assert cancellation_status == CancellationRefundStatus.REFUNDED
        assert len(provider.refund_calls) == 1
    else:
        with pytest.raises(CancellationValidationError, match="within 2 hours"):
            _cancel(records, provider)
        assert provider.refund_calls == []


@pytest.mark.parametrize(
    "payment_status", [PaymentStatus.CREATED, PaymentStatus.FAILED]
)
def test_uncaptured_payment_cancellation_does_not_start_refund(
    cancellation_payment, payment_status
):
    records = cancellation_payment
    db = SessionLocal()
    db.get(Payment, records["payment_id"]).status = payment_status
    db.commit()
    db.close()
    provider = FakeRefundProvider(records)

    _, refund_status = _cancel(records, provider)

    assert refund_status == CancellationRefundStatus.NOT_ELIGIBLE
    assert provider.payment_calls == []
    assert provider.refund_calls == []


def test_recurring_series_cancellation_does_not_start_standalone_refund(
    cancellation_payment,
):
    records = cancellation_payment
    db = SessionLocal()
    appointment = db.get(Appointment, records["appointment_id"])
    payment = db.get(Payment, records["payment_id"])
    series = AppointmentSeries(
        customer_id=records["customer_id"],
        provider_id=records["provider_id"],
        service_id=records["service_id"],
        frequency=AppointmentSeriesFrequency.WEEKLY,
        interval=1,
        start_date=appointment.appointment_start.date(),
        local_start_time=appointment.appointment_start.time().replace(tzinfo=None),
        timezone="UTC",
        end_mode=AppointmentSeriesEndMode.COUNT,
        occurrence_count=2,
        end_date=None,
        status=AppointmentSeriesStatus.ACTIVE,
    )
    db.add(series)
    db.flush()
    appointment.series_id = series.id
    appointment.occurrence_number = 1
    payment.appointment_id = None
    payment.series_id = series.id
    records["series_ids"].append(series.id)
    db.commit()
    assert appointment.series_id == payment.series_id == series.id
    assert payment.status == PaymentStatus.CAPTURED
    assert payment.provider == PaymentProvider.RAZORPAY
    assert payment.provider_order_id == records["provider_order_id"]
    assert payment.provider_payment_id == records["provider_payment_id"]
    db.close()

    provider = FakeRefundProvider(records)
    cancellation_id, cancellation_status = _cancel(records, provider)

    db = SessionLocal()
    appointment = db.get(Appointment, records["appointment_id"])
    cancellation = db.get(AppointmentCancellation, cancellation_id)
    payment = db.get(Payment, records["payment_id"])
    db.close()

    assert appointment.status == AppointmentStatus.CANCELLED
    assert appointment.series_id == payment.series_id == series.id
    assert payment.status == PaymentStatus.CAPTURED
    assert cancellation.refund_status == CancellationRefundStatus.NOT_ELIGIBLE
    assert cancellation_status == CancellationRefundStatus.NOT_ELIGIBLE
    assert provider.payment_calls == []
    assert provider.refund_calls == []


def test_unpaid_cancellation_is_not_refundable(cancellation_payment):
    records = cancellation_payment
    db = SessionLocal()
    db.execute(delete(BookingHold).where(BookingHold.id == records["hold_id"]))
    db.execute(delete(Payment).where(Payment.id == records["payment_id"]))
    db.commit()
    db.close()
    provider = FakeRefundProvider(records)

    _, refund_status = _cancel(records, provider)

    assert refund_status == CancellationRefundStatus.NOT_ELIGIBLE
    assert provider.payment_calls == []
    assert provider.refund_calls == []


def test_expired_unconverted_hold_is_not_refunded(cancellation_payment):
    records = cancellation_payment
    db = SessionLocal()
    db.get(BookingHold, records["hold_id"]).status = BookingHoldStatus.EXPIRED
    db.commit()
    db.close()
    provider = FakeRefundProvider(records)

    _, refund_status = _cancel(records, provider)

    assert refund_status == CancellationRefundStatus.NOT_ELIGIBLE
    assert provider.payment_calls == []
    assert provider.refund_calls == []


def test_missing_booking_hold_is_not_refunded(cancellation_payment):
    records = cancellation_payment
    db = SessionLocal()
    db.execute(delete(BookingHold).where(BookingHold.id == records["hold_id"]))
    db.commit()
    db.close()
    provider = FakeRefundProvider(records)

    _, refund_status = _cancel(records, provider)

    assert refund_status == CancellationRefundStatus.NOT_ELIGIBLE
    assert provider.payment_calls == []
    assert provider.refund_calls == []


def test_provider_capture_mismatch_prevents_refund(cancellation_payment):
    records = cancellation_payment
    provider = FakeRefundProvider(records)
    provider.payment_changes = {"currency": "USD"}

    _, refund_status = _cancel(records, provider)

    assert refund_status == CancellationRefundStatus.NOT_ELIGIBLE
    assert provider.payment_calls == [records["provider_payment_id"]]
    assert provider.refund_calls == []


def test_provider_verification_unavailable_does_not_undo_cancellation(
    cancellation_payment,
):
    records = cancellation_payment
    provider = FakeRefundProvider(records)
    provider.payment_error = RazorpayIntegrationError("provider unavailable")

    cancellation_id, refund_status = _cancel(records, provider)

    db = SessionLocal()
    assert (
        db.get(Appointment, records["appointment_id"]).status
        == AppointmentStatus.CANCELLED
    )
    assert db.get(AppointmentCancellation, cancellation_id).refund_status == (
        CancellationRefundStatus.PENDING
    )
    assert (
        db.scalar(select(Refund).where(Refund.payment_id == records["payment_id"]))
        is None
    )
    db.close()
    assert refund_status == CancellationRefundStatus.PENDING
    assert provider.refund_calls == []


def test_retry_after_provider_verification_failure_can_complete_refund(
    cancellation_payment,
):
    records = cancellation_payment
    provider = FakeRefundProvider(records)
    provider.payment_error = RazorpayIntegrationError("temporarily unavailable")

    first = _cancel(records, provider)
    provider.payment_error = None
    second = _cancel(records, provider)

    assert first[0] == second[0]
    assert second[1] == CancellationRefundStatus.REFUNDED
    assert len(provider.payment_calls) == 2
    assert len(provider.refund_calls) == 1


def test_notification_enqueue_failure_does_not_fail_committed_cancellation(
    cancellation_payment, monkeypatch, caplog
):
    records = cancellation_payment
    provider = FakeRefundProvider(records)

    def fail_enqueue(_appointment_id):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(
        "app.services.booking.send_cancellation_notification.delay",
        fail_enqueue,
    )

    with caplog.at_level("ERROR", logger="app.services.booking"):
        cancellation_id, cancellation_refund_status = _cancel(records, provider)

    db = SessionLocal()
    appointment = db.get(Appointment, records["appointment_id"])
    cancellation = db.get(AppointmentCancellation, cancellation_id)
    refund = db.scalar(select(Refund).where(Refund.payment_id == records["payment_id"]))
    db.close()

    assert appointment.status == AppointmentStatus.CANCELLED
    assert cancellation.refund_status == CancellationRefundStatus.REFUNDED
    assert refund.status == PaymentRefundStatus.PROCESSED
    assert refund.razorpay_refund_id
    assert cancellation_refund_status == CancellationRefundStatus.REFUNDED
    assert len(provider.refund_calls) == 1
    assert "Unable to enqueue cancellation notification" in caplog.text
    assert "redis unavailable" in caplog.text


@pytest.mark.parametrize(
    "failure",
    [
        RazorpayRefundRejectedError("rejected"),
        RazorpayRefundOutcomeUnknownError("timeout"),
    ],
)
def test_refund_provider_failure_preserves_successful_cancellation(
    cancellation_payment, failure
):
    records = cancellation_payment
    provider = FakeRefundProvider(records)
    provider.refund_error = failure

    cancellation_id, refund_status = _cancel(records, provider)

    db = SessionLocal()
    assert (
        db.get(Appointment, records["appointment_id"]).status
        == AppointmentStatus.CANCELLED
    )
    cancellation = db.get(AppointmentCancellation, cancellation_id)
    refund = db.scalar(select(Refund).where(Refund.payment_id == records["payment_id"]))
    db.close()
    assert cancellation.refund_status == CancellationRefundStatus.PENDING
    assert refund_status == CancellationRefundStatus.PENDING
    assert refund.status == (
        PaymentRefundStatus.FAILED
        if isinstance(failure, RazorpayRefundRejectedError)
        else PaymentRefundStatus.PROCESSING
    )


def test_repeated_cancellation_reuses_cancellation_and_refund_intent(
    cancellation_payment,
):
    records = cancellation_payment
    provider = FakeRefundProvider(records)
    first = _cancel(records, provider)
    second = _cancel(records, provider)

    assert first == second
    assert len(provider.refund_calls) == 1
    db = SessionLocal()
    cancellations = db.scalars(
        select(AppointmentCancellation).where(
            AppointmentCancellation.appointment_id == records["appointment_id"]
        )
    ).all()
    refunds = db.scalars(
        select(Refund).where(Refund.payment_id == records["payment_id"])
    ).all()
    db.close()
    assert len(cancellations) == 1
    assert len(refunds) == 1


def test_uncertain_refund_retry_does_not_submit_a_second_provider_request(
    cancellation_payment,
):
    records = cancellation_payment
    provider = FakeRefundProvider(records)
    provider.refund_error = RazorpayRefundOutcomeUnknownError("timeout")

    first = _cancel(records, provider)
    second = _cancel(records, provider)

    assert first == second
    assert first[1] == CancellationRefundStatus.PENDING
    assert len(provider.refund_calls) == 1
    db = SessionLocal()
    refund = db.scalar(select(Refund).where(Refund.payment_id == records["payment_id"]))
    db.close()
    assert refund.status == PaymentRefundStatus.PROCESSING


def test_processed_refund_webhook_updates_cancellation_refund_status(
    cancellation_payment,
):
    records = cancellation_payment
    provider = FakeRefundProvider(records)
    provider.refund_status = "pending"
    _, status = _cancel(records, provider)
    assert status == CancellationRefundStatus.PENDING
    provider.amount_refunded = 12500

    payload = {
        "event": "refund.processed",
        "payload": {
            "refund": {
                "entity": {
                    "entity": "refund",
                    "id": f"rfnd_{records['token'].hex}",
                    "payment_id": records["provider_payment_id"],
                    "amount": 12500,
                    "currency": "INR",
                    "status": "processed",
                }
            },
            "payment": {
                "entity": {
                    "entity": "payment",
                    "id": records["provider_payment_id"],
                    "order_id": records["provider_order_id"],
                    "amount": 12500,
                    "amount_refunded": 12500,
                    "currency": "INR",
                    "status": "captured",
                }
            },
        },
    }
    db = SessionLocal()
    event_status = process_payment_webhook(
        db,
        f"evt_{records['token'].hex}",
        "refund.processed",
        payload,
        razorpay_service=provider,
    )
    cancellation = db.scalar(
        select(AppointmentCancellation).where(
            AppointmentCancellation.appointment_id == records["appointment_id"]
        )
    )
    db.close()

    assert event_status == PaymentWebhookEventStatus.PROCESSED
    assert cancellation.refund_status == CancellationRefundStatus.REFUNDED


def test_admin_reconciliation_syncs_full_refund_without_changing_payment_or_appointment(
    cancellation_payment,
):
    records = cancellation_payment
    provider = FakeRefundProvider(records)
    provider.refund_status = "pending"
    _, cancellation_status = _cancel(records, provider)
    assert cancellation_status == CancellationRefundStatus.PENDING
    provider.amount_refunded = 12500

    db = SessionLocal()
    refund = db.scalar(select(Refund).where(Refund.payment_id == records["payment_id"]))
    assert refund is not None
    reconciled = reconcile_processing_refund(
        db,
        refund.id,
        razorpay_service=provider,
    )
    appointment = db.get(Appointment, records["appointment_id"])
    payment = db.get(Payment, records["payment_id"])
    cancellation = db.scalar(
        select(AppointmentCancellation).where(
            AppointmentCancellation.appointment_id == records["appointment_id"]
        )
    )
    db.close()

    assert reconciled.status == PaymentRefundStatus.PROCESSED
    assert appointment.status == AppointmentStatus.CANCELLED
    assert payment.status == PaymentStatus.CAPTURED
    assert cancellation.refund_status == CancellationRefundStatus.REFUNDED
    assert len(provider.refund_calls) == 1


def test_failed_refund_with_pending_cancellation_is_a_candidate(
    cancellation_payment,
):
    records = cancellation_payment
    db = SessionLocal()
    appointment = db.get(Appointment, records["appointment_id"])
    appointment.status = AppointmentStatus.CANCELLED
    cancellation = AppointmentCancellation(
        appointment_id=records["appointment_id"],
        cancelled_by="customer",
        reason="Appointment cancelled",
        refund_status=CancellationRefundStatus.PENDING,
    )
    refund = Refund(
        payment_id=records["payment_id"],
        amount=12500,
        currency="INR",
        status=PaymentRefundStatus.FAILED,
        razorpay_refund_id=f"rfnd_{records['token'].hex}",
        idempotency_key=f"failed-cancellation-{records['token']}",
        reason="Appointment cancelled",
    )
    db.add_all([cancellation, refund])
    db.commit()

    candidates = list_refund_reconciliation_candidates(db)
    candidate = next(item for item in candidates if item.refund_id == refund.id)
    db.close()

    assert (
        RefundReconciliationReason.PENDING_CANCELLATION_REFUND
        in candidate.investigation_reasons
    )


def test_reconciliation_repairs_interrupted_full_refund_cancellation_sync(
    cancellation_payment,
):
    records = cancellation_payment
    db = SessionLocal()
    cancellation = AppointmentCancellation(
        appointment_id=records["appointment_id"],
        cancelled_by="customer",
        reason="Appointment cancelled",
        refund_status=CancellationRefundStatus.PENDING,
    )
    appointment = db.get(Appointment, records["appointment_id"])
    appointment.status = AppointmentStatus.CANCELLED
    refund = Refund(
        payment_id=records["payment_id"],
        amount=12500,
        currency="INR",
        status=PaymentRefundStatus.PROCESSED,
        razorpay_refund_id=f"rfnd_{records['token'].hex}",
        idempotency_key=f"interrupted-sync-{records['token']}",
        reason="Appointment cancelled",
    )
    db.add_all([cancellation, refund])
    db.commit()
    provider = FakeRefundProvider(records)
    provider.amount_refunded = 12500

    candidates = list_refund_reconciliation_candidates(db)
    assert any(
        candidate.refund_id == refund.id
        and RefundReconciliationReason.PENDING_CANCELLATION_REFUND
        in candidate.investigation_reasons
        for candidate in candidates
    )

    reconciled = reconcile_processing_refund(
        db,
        refund.id,
        razorpay_service=provider,
    )
    db.refresh(cancellation)
    appointment = db.get(Appointment, records["appointment_id"])
    payment = db.get(Payment, records["payment_id"])
    db.close()

    assert reconciled.status == PaymentRefundStatus.PROCESSED
    assert cancellation.refund_status == CancellationRefundStatus.REFUNDED
    assert appointment.status == AppointmentStatus.CANCELLED
    assert payment.status == PaymentStatus.CAPTURED


def test_customer_cannot_cancel_another_customers_appointment(cancellation_payment):
    records = cancellation_payment
    db = SessionLocal()
    with pytest.raises(CancellationValidationError, match="Appointment not found"):
        cancel_appointment(
            db,
            records["appointment_id"],
            AppointmentCancellationCreate(),
            user_role=UserRole.CUSTOMER,
            customer_id=records["other_customer_id"],
        )
    db.rollback()
    db.close()


def test_customer_route_preserves_ownership_check(cancellation_payment):
    records = cancellation_payment
    db = SessionLocal()
    other = db.get(User, records["other_customer_id"])
    token = create_access_token(other.id, other.role)
    db.close()

    response = client.post(
        f"/api/customer/appointments/{records['appointment_id']}/cancel",
        json={"reason": "not my appointment"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("post", "/api/appointments/{appointment_id}/cancel", {"reason": "test"}),
        ("delete", "/api/appointments/{appointment_id}", None),
    ],
)
def test_general_cancellation_routes_reject_non_owner_customer(
    cancellation_payment, method, path, json
):
    records = cancellation_payment
    db = SessionLocal()
    other = db.get(User, records["other_customer_id"])
    token = create_access_token(other.id, other.role)
    db.close()

    response = client.request(
        method.upper(),
        path.format(appointment_id=records["appointment_id"]),
        json=json,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_cancellation_rejects_caller_supplied_refund_status(cancellation_payment):
    records = cancellation_payment
    db = SessionLocal()
    customer = db.get(User, records["customer_id"])
    token = create_access_token(customer.id, customer.role)
    db.close()

    response = client.post(
        f"/api/customer/appointments/{records['appointment_id']}/cancel",
        json={"refund_status": "refunded"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    db = SessionLocal()
    assert (
        db.get(Appointment, records["appointment_id"]).status
        == AppointmentStatus.CONFIRMED
    )
    db.close()
