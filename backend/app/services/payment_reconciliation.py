from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.booking_hold import BookingHold, BookingHoldStatus
from app.models.payment import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    PaymentWebhookEvent,
    PaymentWebhookEventStatus,
)
from app.schemas.payment_reconciliation import (
    PaymentReconciliationCandidate,
    PaymentReconciliationEvent,
    PaymentReconciliationHold,
    PaymentReconciliationReason,
)

MAX_RECONCILIATION_CANDIDATES = 500


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")


def _candidate_reasons(
    payment: Payment,
    holds: list[BookingHold],
    events: list[PaymentWebhookEvent],
    as_of: datetime,
) -> list[PaymentReconciliationReason]:
    reasons: set[PaymentReconciliationReason] = set()
    validation_failed_events = [
        event for event in events if event.capture_validation_failure is not None
    ]
    if validation_failed_events:
        reasons.add(PaymentReconciliationReason.CAPTURE_VALIDATION_FAILED)
    if (
        payment.status == PaymentStatus.CAPTURED
        and payment.appointment_id is None
        and payment.series_id is None
    ):
        reasons.add(PaymentReconciliationReason.CAPTURED_UNLINKED)
    elif payment.status == PaymentStatus.CREATED and not validation_failed_events:
        reasons.add(PaymentReconciliationReason.STALE_CREATED_NO_CAPTURE_EVIDENCE)

    if not payment.provider_order_id:
        reasons.add(PaymentReconciliationReason.MISSING_LOCAL_PROVIDER_ORDER_ID)
    if not payment.provider_payment_id:
        reasons.add(PaymentReconciliationReason.MISSING_LOCAL_PROVIDER_PAYMENT_ID)

    for hold in holds:
        if hold.status == BookingHoldStatus.RELEASED:
            reasons.add(PaymentReconciliationReason.RELEASED_HOLD)
        elif hold.status == BookingHoldStatus.EXPIRED or hold.expires_at <= as_of:
            reasons.add(PaymentReconciliationReason.EXPIRED_HOLD)

    for event in events:
        if event.capture_validation_failure is not None:
            reasons.add(PaymentReconciliationReason.CAPTURE_VALIDATION_FAILED)
        if event.local_payment_state_conflict:
            reasons.add(PaymentReconciliationReason.LOCAL_PAYMENT_STATE_CONFLICT)
        if event.status == PaymentWebhookEventStatus.RETRYABLE:
            reasons.add(PaymentReconciliationReason.RETRYABLE_WEBHOOK_EVENT)
        elif event.status == PaymentWebhookEventStatus.FAILED:
            reasons.add(PaymentReconciliationReason.FAILED_WEBHOOK_EVENT)

        if (
            payment.provider_order_id
            and event.provider_order_id
            and payment.provider_order_id != event.provider_order_id
        ):
            reasons.add(PaymentReconciliationReason.MISMATCHED_PROVIDER_ORDER_ID)
        if (
            payment.provider_payment_id
            and event.provider_payment_id
            and payment.provider_payment_id != event.provider_payment_id
        ):
            reasons.add(PaymentReconciliationReason.MISMATCHED_PROVIDER_PAYMENT_ID)

    return sorted(reasons, key=lambda reason: reason.value)


def list_payment_reconciliation_candidates(
    db: Session,
    *,
    stale_created_before: datetime,
    as_of: datetime | None = None,
    limit: int = 100,
) -> list[PaymentReconciliationCandidate]:
    """List bounded local candidates; this does not verify capture with Razorpay."""
    _require_aware(stale_created_before, "stale_created_before")
    as_of = as_of or datetime.now(UTC)
    _require_aware(as_of, "as_of")
    if not 1 <= limit <= MAX_RECONCILIATION_CANDIDATES:
        raise ValueError(f"limit must be between 1 and {MAX_RECONCILIATION_CANDIDATES}")

    expired_or_released_hold = (
        select(BookingHold.id)
        .where(
            BookingHold.payment_id == Payment.id,
            or_(
                BookingHold.status.in_(
                    [BookingHoldStatus.EXPIRED, BookingHoldStatus.RELEASED]
                ),
                BookingHold.expires_at <= as_of,
            ),
        )
        .exists()
    )
    investigation_event = (
        select(PaymentWebhookEvent.id)
        .where(
            or_(
                PaymentWebhookEvent.capture_validation_failure.is_not(None),
                PaymentWebhookEvent.local_payment_state_conflict.is_(True),
            ),
            or_(
                and_(
                    Payment.provider_order_id.is_not(None),
                    PaymentWebhookEvent.provider_order_id == Payment.provider_order_id,
                ),
                and_(
                    Payment.provider_payment_id.is_not(None),
                    PaymentWebhookEvent.provider_payment_id
                    == Payment.provider_payment_id,
                ),
            ),
        )
        .exists()
    )
    candidate_query = (
        select(Payment)
        .where(
            Payment.provider == PaymentProvider.RAZORPAY,
            or_(
                and_(
                    Payment.appointment_id.is_(None),
                    Payment.series_id.is_(None),
                    or_(
                        Payment.status == PaymentStatus.CAPTURED,
                        and_(
                            Payment.status == PaymentStatus.CREATED,
                            Payment.provider_order_id.is_not(None),
                            Payment.created_at <= stale_created_before,
                            expired_or_released_hold,
                        ),
                    ),
                ),
                investigation_event,
            ),
        )
        .order_by(Payment.created_at, Payment.id)
        .limit(limit)
    )
    payments = db.scalars(candidate_query).all()
    if not payments:
        return []

    payment_ids = [payment.id for payment in payments]
    holds_by_payment: dict[UUID, list[BookingHold]] = {
        payment_id: [] for payment_id in payment_ids
    }
    for hold in db.scalars(
        select(BookingHold)
        .where(BookingHold.payment_id.in_(payment_ids))
        .order_by(BookingHold.created_at, BookingHold.id)
    ).all():
        if hold.payment_id in holds_by_payment:
            holds_by_payment[hold.payment_id].append(hold)

    order_ids = {
        payment.provider_order_id
        for payment in payments
        if payment.provider_order_id is not None
    }
    provider_payment_ids = {
        payment.provider_payment_id
        for payment in payments
        if payment.provider_payment_id is not None
    }
    matching_events: list[PaymentWebhookEvent] = []
    if order_ids or provider_payment_ids:
        matching_events = db.scalars(
            select(PaymentWebhookEvent)
            .where(
                or_(
                    PaymentWebhookEvent.provider_order_id.in_(order_ids)
                    if order_ids
                    else False,
                    PaymentWebhookEvent.provider_payment_id.in_(provider_payment_ids)
                    if provider_payment_ids
                    else False,
                )
            )
            .order_by(PaymentWebhookEvent.created_at, PaymentWebhookEvent.id)
        ).all()

    results = []
    for payment in payments:
        holds = holds_by_payment[payment.id]
        events = [
            event
            for event in matching_events
            if (
                payment.provider_order_id is not None
                and event.provider_order_id == payment.provider_order_id
            )
            or (
                payment.provider_payment_id is not None
                and event.provider_payment_id == payment.provider_payment_id
            )
        ]
        results.append(
            PaymentReconciliationCandidate(
                payment_id=payment.id,
                status=payment.status,
                amount=payment.amount,
                currency=payment.currency,
                provider_order_id=payment.provider_order_id,
                provider_payment_id=payment.provider_payment_id,
                appointment_id=payment.appointment_id,
                series_id=payment.series_id,
                created_at=payment.created_at,
                updated_at=payment.updated_at,
                reasons=_candidate_reasons(payment, holds, events, as_of),
                booking_holds=[
                    PaymentReconciliationHold.model_validate(hold) for hold in holds
                ],
                webhook_events=[
                    PaymentReconciliationEvent.model_validate(event) for event in events
                ],
            )
        )
    return results
