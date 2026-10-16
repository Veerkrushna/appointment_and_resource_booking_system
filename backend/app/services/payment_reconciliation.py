from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.orm import Session, aliased

from app.models.appointment import Appointment
from app.models.appointment_cancellation import AppointmentCancellation
from app.models.appointment_cancellation import (
    RefundStatus as AppointmentCancellationRefundStatus,
)
from app.models.booking_hold import BookingHold, BookingHoldStatus
from app.models.payment import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    PaymentWebhookEvent,
    PaymentWebhookEventStatus,
)
from app.models.refund import PaymentRefundStatus, Refund
from app.schemas.payment_reconciliation import (
    PaymentReconciliationCandidate,
    PaymentReconciliationEvent,
    PaymentReconciliationHold,
    PaymentReconciliationReason,
    RefundReconciliationCandidate,
    RefundReconciliationReason,
)
from app.services.payment_verification import _appointment_matches_hold

MAX_RECONCILIATION_CANDIDATES = 500
_UNRESOLVED_REFUND_STATUSES = {
    PaymentRefundStatus.PENDING,
    PaymentRefundStatus.PROCESSING,
}


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")


def _candidate_reasons(
    payment: Payment,
    holds: list[BookingHold],
    events: list[PaymentWebhookEvent],
    as_of: datetime,
    *,
    inconsistent_appointment_link: bool = False,
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

    if inconsistent_appointment_link:
        reasons.add(PaymentReconciliationReason.INCONSISTENT_APPOINTMENT_LINK)

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
    all_payment_holds = aliased(BookingHold)
    consistent_appointment_link = (
        select(Appointment.id)
        .join(BookingHold, BookingHold.payment_id == Payment.id)
        .where(
            Appointment.id == Payment.appointment_id,
            Appointment.customer_id == Payment.customer_id,
            Appointment.service_id == BookingHold.service_id,
            Appointment.provider_id == BookingHold.provider_id,
            BookingHold.status == BookingHoldStatus.CONVERTED,
            Payment.status == PaymentStatus.CAPTURED,
            Payment.provider_payment_id.is_not(None),
            Payment.series_id.is_(None),
            select(func.count(all_payment_holds.id))
            .where(all_payment_holds.payment_id == Payment.id)
            .scalar_subquery()
            == 1,
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
                and_(
                    Payment.appointment_id.is_not(None),
                    not_(consistent_appointment_link),
                ),
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
                reasons=_candidate_reasons(
                    payment,
                    holds,
                    events,
                    as_of,
                    inconsistent_appointment_link=(
                        payment.appointment_id is not None
                        and (
                            len(holds) != 1
                            or not _appointment_matches_hold(
                                payment,
                                holds[0],
                                db.get(Appointment, payment.appointment_id),
                            )
                        )
                    ),
                ),
                booking_holds=[
                    PaymentReconciliationHold.model_validate(hold) for hold in holds
                ],
                webhook_events=[
                    PaymentReconciliationEvent.model_validate(event) for event in events
                ],
            )
        )
    return results


def list_refund_reconciliation_candidates(
    db: Session,
    *,
    limit: int = 100,
) -> list[RefundReconciliationCandidate]:
    """List bounded local refund intents that need investigation.

    Pending/processing intents are unresolved. Other statuses are included
    only when persisted payment or webhook records reveal an inconsistency.
    This query never contacts Razorpay or updates records.
    """
    if not 1 <= limit <= MAX_RECONCILIATION_CANDIDATES:
        raise ValueError(f"limit must be between 1 and {MAX_RECONCILIATION_CANDIDATES}")

    matching_refund_events = select(PaymentWebhookEvent.id).where(
        PaymentWebhookEvent.provider_refund_id == Refund.razorpay_refund_id
    )
    webhook_payment_mismatch = matching_refund_events.where(
        PaymentWebhookEvent.provider_payment_id.is_not(None),
        Payment.provider_payment_id.is_not(None),
        PaymentWebhookEvent.provider_payment_id != Payment.provider_payment_id,
    ).exists()
    webhook_order_mismatch = matching_refund_events.where(
        PaymentWebhookEvent.provider_order_id.is_not(None),
        Payment.provider_order_id.is_not(None),
        PaymentWebhookEvent.provider_order_id != Payment.provider_order_id,
    ).exists()
    pending_cancellation_refund = (
        select(AppointmentCancellation.id)
        .where(
            AppointmentCancellation.appointment_id == Payment.appointment_id,
            AppointmentCancellation.refund_status
            == AppointmentCancellationRefundStatus.PENDING,
        )
        .exists()
    )
    reserved_refund_amount = (
        select(func.coalesce(func.sum(Refund.amount), 0))
        .where(
            Refund.payment_id == Payment.id,
            Refund.status.in_(
                {
                    PaymentRefundStatus.PENDING,
                    PaymentRefundStatus.PROCESSING,
                    PaymentRefundStatus.PROCESSED,
                }
            ),
        )
        .correlate(Payment)
        .scalar_subquery()
    )
    candidate_query = (
        select(
            Refund,
            Payment,
            webhook_payment_mismatch.label("webhook_payment_mismatch"),
            webhook_order_mismatch.label("webhook_order_mismatch"),
            pending_cancellation_refund.label("pending_cancellation_refund"),
            (reserved_refund_amount > Payment.amount).label(
                "refund_reservations_exceed_payment"
            ),
        )
        .outerjoin(Payment, Payment.id == Refund.payment_id)
        .where(
            or_(
                Refund.status.in_(_UNRESOLVED_REFUND_STATUSES),
                Payment.id.is_(None),
                Refund.amount <= 0,
                and_(Payment.id.is_not(None), Refund.amount > Payment.amount),
                and_(
                    Payment.id.is_not(None),
                    reserved_refund_amount > Payment.amount,
                ),
                and_(
                    Payment.id.is_not(None),
                    Refund.currency != Payment.currency,
                ),
                and_(
                    Refund.status == PaymentRefundStatus.PROCESSED,
                    Refund.razorpay_refund_id.is_(None),
                ),
                and_(
                    Payment.id.is_not(None),
                    Payment.provider_payment_id.is_(None),
                ),
                and_(Payment.id.is_not(None), Payment.provider_order_id.is_(None)),
                and_(
                    Payment.id.is_not(None),
                    Payment.provider != PaymentProvider.RAZORPAY,
                ),
                webhook_payment_mismatch,
                webhook_order_mismatch,
                pending_cancellation_refund,
            )
        )
        .order_by(Refund.created_at, Refund.id)
        .limit(limit)
    )
    rows = db.execute(candidate_query).all()
    if not rows:
        return []

    candidates = []
    for (
        refund,
        payment,
        payment_mismatch,
        order_mismatch,
        cancellation_refund_pending,
        reservations_exceed_payment,
    ) in rows:
        reasons: set[RefundReconciliationReason] = set()
        if refund.status == PaymentRefundStatus.PENDING:
            reasons.add(RefundReconciliationReason.REFUND_PENDING)
        elif refund.status == PaymentRefundStatus.PROCESSING:
            reasons.add(RefundReconciliationReason.REFUND_PROCESSING)

        if payment is None:
            reasons.add(RefundReconciliationReason.MISSING_PAYMENT)
        else:
            if refund.amount <= 0 or refund.amount > payment.amount:
                reasons.add(RefundReconciliationReason.INVALID_REFUND_AMOUNT)
            if refund.currency != payment.currency:
                reasons.add(RefundReconciliationReason.REFUND_CURRENCY_MISMATCH)
            if reservations_exceed_payment:
                reasons.add(
                    RefundReconciliationReason.REFUND_RESERVATIONS_EXCEED_PAYMENT
                )
            if refund.razorpay_refund_id is None and (
                refund.status in _UNRESOLVED_REFUND_STATUSES
                or refund.status == PaymentRefundStatus.PROCESSED
            ):
                reasons.add(RefundReconciliationReason.MISSING_PROVIDER_REFUND_ID)
            if payment.provider_payment_id is None:
                reasons.add(RefundReconciliationReason.MISSING_PROVIDER_PAYMENT_ID)
            if payment.provider_order_id is None:
                reasons.add(RefundReconciliationReason.MISSING_PROVIDER_ORDER_ID)
            if payment.provider != PaymentProvider.RAZORPAY:
                reasons.add(RefundReconciliationReason.NON_RAZORPAY_PAYMENT)

            if payment_mismatch:
                reasons.add(RefundReconciliationReason.MISMATCHED_WEBHOOK_PAYMENT_ID)
            if order_mismatch:
                reasons.add(RefundReconciliationReason.MISMATCHED_WEBHOOK_ORDER_ID)
            if cancellation_refund_pending:
                reasons.add(RefundReconciliationReason.PENDING_CANCELLATION_REFUND)

        candidates.append(
            RefundReconciliationCandidate(
                refund_id=refund.id,
                status=refund.status,
                amount=refund.amount,
                currency=refund.currency,
                razorpay_refund_id=refund.razorpay_refund_id,
                refund_reason=refund.reason,
                payment_id=refund.payment_id,
                provider_payment_id=(
                    payment.provider_payment_id if payment is not None else None
                ),
                provider_order_id=(
                    payment.provider_order_id if payment is not None else None
                ),
                created_at=refund.created_at,
                updated_at=refund.updated_at,
                investigation_reasons=sorted(reasons, key=lambda reason: reason.value),
            )
        )
    return candidates
