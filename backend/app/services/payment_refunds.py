import logging
import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.appointment_cancellation import (
    AppointmentCancellation,
)
from app.models.appointment_cancellation import (
    RefundStatus as AppointmentCancellationRefundStatus,
)
from app.models.payment import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    PaymentWebhookEvent,
    PaymentWebhookEventStatus,
)
from app.models.refund import PaymentRefundStatus, Refund
from app.services.razorpay import (
    RazorpayIntegrationError,
    RazorpayRefundNotSubmittedError,
    RazorpayRefundOutcomeUnknownError,
    RazorpayRefundRejectedError,
    RazorpayService,
)

logger = logging.getLogger(__name__)

RefundReconciliationOutcomeType = Literal[
    "updated",
    "unchanged",
    "no_matching_refund",
    "multiple_matching_refunds",
    "provider_unavailable",
    "evidence_conflict",
]


class RefundValidationError(ValueError):
    pass


class RefundConflictError(ValueError):
    pass


class RefundNotFoundError(LookupError):
    pass


class RefundPersistenceError(RuntimeError):
    pass


class RefundOutcomeUnknownError(RuntimeError):
    def __init__(
        self, message: str, *, failure_classification: str = "evidence_unverifiable"
    ):
        super().__init__(message)
        self.failure_classification = failure_classification


class RefundHistoryNoMatchError(RefundOutcomeUnknownError):
    pass


class RefundHistoryAmbiguousError(RefundOutcomeUnknownError):
    pass


class RefundHistoryInvalidError(RefundOutcomeUnknownError):
    pass


@dataclass(frozen=True)
class RefundReconciliationOutcome:
    refund: Refund
    previous_status: PaymentRefundStatus
    outcome: RefundReconciliationOutcomeType
    failure_classification: str | None = None


_RESERVED_REFUND_STATUSES = {
    PaymentRefundStatus.PENDING,
    PaymentRefundStatus.PROCESSING,
    PaymentRefundStatus.PROCESSED,
}
_IDEMPOTENCY_KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]{10,255}\Z")
_PROVIDER_REFUND_STATUSES = {
    "pending": PaymentRefundStatus.PROCESSING,
    "processed": PaymentRefundStatus.PROCESSED,
    "failed": PaymentRefundStatus.FAILED,
}


def _load_locked_payment(db: Session, payment_id: UUID) -> Payment | None:
    return db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())


def _load_refund_by_key(db: Session, idempotency_key: str) -> Refund | None:
    return db.scalar(select(Refund).where(Refund.idempotency_key == idempotency_key))


def _return_existing_refund(
    refund: Refund | None,
    payment_id: UUID,
    amount: int | None = None,
    currency: str | None = None,
) -> Refund | None:
    if refund is None:
        return None
    if (
        refund.payment_id != payment_id
        or (amount is not None and refund.amount != amount)
        or (currency is not None and refund.currency != currency)
    ):
        raise RefundConflictError("Idempotency key is already used for another refund")
    return refund


def _verify_captured_payment(
    payment: Payment, provider: RazorpayService
) -> tuple[int, int]:
    if payment.provider != PaymentProvider.RAZORPAY:
        raise RefundValidationError("Payment provider does not support refunds")
    if payment.status != PaymentStatus.CAPTURED:
        raise RefundValidationError("Only captured payments can be refunded")
    if not payment.provider_order_id:
        raise RefundValidationError("Payment has no Razorpay order ID")
    if not payment.provider_payment_id:
        raise RefundValidationError("Payment has no Razorpay payment ID")

    evidence = provider.fetch_payment(payment.provider_payment_id)
    if not isinstance(evidence, dict):
        raise RefundValidationError("Razorpay payment evidence is invalid")
    provider_amount = evidence.get("amount")
    amount_refunded = evidence.get("amount_refunded")
    if (
        evidence.get("id") != payment.provider_payment_id
        or evidence.get("order_id") != payment.provider_order_id
        or evidence.get("status") != "captured"
        or type(provider_amount) is not int
        or provider_amount <= 0
        or provider_amount != payment.amount
        or evidence.get("currency") != payment.currency
        or type(amount_refunded) is not int
        or amount_refunded < 0
        or amount_refunded > provider_amount
    ):
        raise RefundValidationError(
            "Razorpay payment evidence does not match the stored payment"
        )
    return provider_amount, amount_refunded


def _reserved_amounts(db: Session, payment_id: UUID) -> tuple[int, int]:
    refunds = db.scalars(
        select(Refund).where(
            Refund.payment_id == payment_id,
            Refund.status.in_(_RESERVED_REFUND_STATUSES),
        )
    ).all()
    processed = sum(
        refund.amount
        for refund in refunds
        if refund.status == PaymentRefundStatus.PROCESSED
    )
    pending = sum(
        refund.amount
        for refund in refunds
        if refund.status
        in {PaymentRefundStatus.PENDING, PaymentRefundStatus.PROCESSING}
    )
    return processed, pending


def _persist_intent(
    db: Session,
    payment: Payment,
    amount: int,
    idempotency_key: str,
    reason: str,
) -> Refund:
    refund = Refund(
        payment_id=payment.id,
        amount=amount,
        currency=payment.currency,
        status=PaymentRefundStatus.PROCESSING,
        idempotency_key=idempotency_key,
        reason=reason,
    )
    db.add(refund)
    try:
        db.commit()
        db.refresh(refund)
        return refund
    except SQLAlchemyError as error:
        db.rollback()
        persisted = _load_refund_by_key(db, idempotency_key)
        if persisted is not None and persisted.payment_id != payment.id:
            raise RefundConflictError(
                "Idempotency key is already used for another refund"
            ) from error
        if (
            persisted is not None
            and persisted.payment_id == payment.id
            and persisted.amount == amount
            and persisted.currency == payment.currency
            and persisted.status == PaymentRefundStatus.PROCESSING
            and persisted.razorpay_refund_id is None
        ):
            return persisted
        raise RefundPersistenceError(
            "Unable to confirm persisted refund intent"
        ) from error


def _persist_provider_result(
    db: Session,
    refund: Refund,
    provider_refund_id: str,
    status: PaymentRefundStatus,
) -> Refund:
    refund.razorpay_refund_id = provider_refund_id
    refund.status = status
    try:
        db.commit()
        db.refresh(refund)
        return refund
    except SQLAlchemyError as error:
        logger.error(
            "Unable to persist successful Razorpay refund response",
            extra={
                "refund_event": "provider_result_persistence_failed",
                "refund_id": str(refund.id),
                "payment_id": str(refund.payment_id),
                "amount": refund.amount,
                "currency": refund.currency,
                "provider_response_status": status.value,
                "provider_refund_id_returned": bool(provider_refund_id),
                "failure_classification": "database_persistence_failure",
            },
        )
        refund_id = refund.id
        idempotency_key = refund.idempotency_key
        db.rollback()
        persisted = _load_refund_by_key(db, idempotency_key)
        if (
            persisted is not None
            and persisted.id == refund_id
            and persisted.razorpay_refund_id == provider_refund_id
            and persisted.status == status
        ):
            return persisted
        raise RefundOutcomeUnknownError(
            "Razorpay refund may have succeeded; reconciliation is required"
        ) from error


def _mark_definitive_failure(db: Session, refund: Refund) -> None:
    refund.status = PaymentRefundStatus.FAILED
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.error(
            "Unable to persist definitive refund rejection",
            extra={
                "refund_event": "rejection_persistence_failed",
                "refund_id": str(refund.id),
                "payment_id": str(refund.payment_id),
                "amount": refund.amount,
                "currency": refund.currency,
                "provider_refund_id_returned": False,
                "failure_classification": "database_persistence_failure",
            },
        )


def _provider_result_status(
    result: dict, provider_payment_id: str, currency: str, amount: int
) -> tuple[str, PaymentRefundStatus]:
    if not isinstance(result, dict):
        raise RefundOutcomeUnknownError(
            "Razorpay refund response could not be verified"
        )
    refund_id = result.get("id")
    result_amount = result.get("amount")
    provider_status = result.get("status")
    if (
        not isinstance(refund_id, str)
        or not refund_id
        or len(refund_id) > 255
        or result.get("payment_id") != provider_payment_id
        or type(result_amount) is not int
        or result_amount != amount
        or result.get("currency") != currency
    ):
        raise RefundOutcomeUnknownError(
            "Razorpay refund response could not be verified"
        )

    if (
        not isinstance(provider_status, str)
        or provider_status not in _PROVIDER_REFUND_STATUSES
    ):
        raise RefundOutcomeUnknownError(
            "Razorpay refund response has an unresolved status"
        )
    return refund_id, _PROVIDER_REFUND_STATUSES[provider_status]


def _refund_provider_status(
    evidence: object, refund: Refund, payment: Payment
) -> tuple[str, PaymentRefundStatus]:
    if not isinstance(evidence, dict):
        raise RefundOutcomeUnknownError(
            "Razorpay refund evidence is invalid",
            failure_classification="refund_response_shape_invalid",
        )
    provider_refund_id = evidence.get("id")
    provider_amount = evidence.get("amount")
    provider_status = evidence.get("status")
    if provider_refund_id != refund.razorpay_refund_id:
        raise RefundOutcomeUnknownError(
            "Razorpay refund ID does not match the local refund",
            failure_classification="provider_refund_id_mismatch",
        )
    if evidence.get("payment_id") != payment.provider_payment_id:
        raise RefundOutcomeUnknownError(
            "Razorpay refund payment ID does not match the local payment",
            failure_classification="provider_payment_id_mismatch",
        )
    if type(provider_amount) is not int or provider_amount != refund.amount:
        raise RefundOutcomeUnknownError(
            "Razorpay refund amount does not match the local refund",
            failure_classification="refund_amount_mismatch",
        )
    if evidence.get("currency") != refund.currency:
        raise RefundOutcomeUnknownError(
            "Razorpay refund currency does not match the local refund",
            failure_classification="refund_currency_mismatch",
        )
    if not isinstance(provider_status, str):
        raise RefundOutcomeUnknownError(
            "Razorpay refund status is missing or invalid",
            failure_classification="refund_status_invalid",
        )
    if provider_status not in _PROVIDER_REFUND_STATUSES:
        raise RefundOutcomeUnknownError(
            "Razorpay refund status is not recognized",
            failure_classification="refund_status_unrecognized",
        )
    return provider_refund_id, _PROVIDER_REFUND_STATUSES[provider_status]


def _find_provider_refund_id(
    provider: RazorpayService,
    payment: Payment,
    refund: Refund,
) -> tuple[str, PaymentRefundStatus]:
    if refund.amount != payment.amount:
        raise RefundValidationError(
            "Only full refunds can be recovered from provider refund history"
        )

    collection = provider.fetch_payment_refunds(payment.provider_payment_id)
    if (
        not isinstance(collection, dict)
        or collection.get("entity") != "collection"
        or not isinstance(collection.get("items"), list)
        or type(collection.get("count")) is not int
        or collection["count"] != len(collection["items"])
        or collection.get("has_more") is True
    ):
        raise RefundHistoryInvalidError(
            "Razorpay refund history is incomplete or invalid"
        )
    if not collection["items"]:
        raise RefundHistoryNoMatchError(
            "Razorpay refund history is empty; the local refund remains unchanged",
            failure_classification="provider_refund_history_empty",
        )

    matches = []
    for item in collection["items"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not item["id"]
            or item.get("payment_id") != payment.provider_payment_id
            or type(item.get("amount")) is not int
            or item.get("currency") != payment.currency
            or not isinstance(item.get("status"), str)
            or item["status"] not in _PROVIDER_REFUND_STATUSES
            or type(item.get("created_at")) is not int
            or item["created_at"] < 0
        ):
            raise RefundHistoryInvalidError(
                "Razorpay refund history contains unverifiable records"
            )
        if item["amount"] == refund.amount and item["created_at"] >= int(
            refund.created_at.timestamp()
        ):
            matches.append((item["id"], _PROVIDER_REFUND_STATUSES[item["status"]]))

    if not matches:
        raise RefundHistoryNoMatchError(
            "No matching Razorpay refund was found; the local refund remains unchanged"
        )
    if len(matches) > 1:
        raise RefundHistoryAmbiguousError(
            "Multiple matching Razorpay refunds were found; the local refund remains unchanged"
        )
    return matches[0]


def _unchanged_refund_outcome(
    db: Session,
    refund_id: UUID,
    previous_status: PaymentRefundStatus,
    actor_id: UUID | None,
    outcome: RefundReconciliationOutcomeType,
    *,
    failure_classification: str | None = None,
    error: Exception | None = None,
) -> RefundReconciliationOutcome:
    db.rollback()
    refund = db.get(Refund, refund_id)
    if refund is None:
        raise RefundNotFoundError("Refund was not found")
    if failure_classification is not None:
        cause = error.__cause__ if error is not None else None
        exception_name = type(cause or error).__name__ if error is not None else None
        logger.warning(
            "Admin refund reconciliation left state unchanged: %s",
            failure_classification,
            extra={
                "refund_id": str(refund_id),
                "failure_classification": failure_classification,
                "exception_class": (
                    exception_name
                    if isinstance(exception_name, str)
                    and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", exception_name)
                    else None
                ),
                "provider_http_status": getattr(error, "provider_http_status", None),
            },
        )
    _log_admin_refund_reconciliation(
        actor_id,
        refund_id,
        previous_status,
        refund.status,
        outcome,
    )
    return RefundReconciliationOutcome(
        refund, previous_status, outcome, failure_classification
    )


def _refund_payment_evidence(
    evidence: object,
    payment: Payment,
    refund_amount: int | None = None,
    *,
    allow_fully_refunded: bool = False,
) -> bool:
    return (
        _refund_payment_evidence_failure(
            evidence,
            payment,
            refund_amount,
            allow_fully_refunded=allow_fully_refunded,
        )
        is None
    )


def _refund_payment_evidence_failure(
    evidence: object,
    payment: Payment,
    refund_amount: int | None = None,
    *,
    allow_fully_refunded: bool = False,
) -> str | None:
    if not isinstance(evidence, dict):
        return "payment_response_shape_invalid"
    if evidence.get("id") != payment.provider_payment_id:
        return "provider_payment_id_mismatch"
    if evidence.get("order_id") != payment.provider_order_id:
        return "provider_order_id_mismatch"
    provider_amount = evidence.get("amount")
    if type(provider_amount) is not int or provider_amount != payment.amount:
        return "payment_amount_mismatch"
    if evidence.get("currency") != payment.currency:
        return "payment_currency_mismatch"
    amount_refunded = evidence.get("amount_refunded")
    if type(amount_refunded) is not int or not 0 <= amount_refunded <= payment.amount:
        return "payment_refunded_total_invalid"
    provider_status = evidence.get("status")
    if provider_status == "captured":
        pass
    elif provider_status == "refunded":
        if not allow_fully_refunded:
            return "provider_payment_not_captured"
        if amount_refunded != payment.amount:
            return "payment_refunded_status_total_mismatch"
    else:
        return "provider_payment_not_captured"
    if refund_amount is not None and amount_refunded < refund_amount:
        return "payment_refunded_total_below_refund"
    return None


def _persist_reconciled_status(
    db: Session,
    refund: Refund,
    payment: Payment,
    target_status: PaymentRefundStatus,
) -> Refund:
    if refund.status in {
        PaymentRefundStatus.PROCESSED,
        PaymentRefundStatus.FAILED,
    }:
        if refund.status != target_status:
            raise RefundConflictError(
                "Provider refund state conflicts with a terminal local state"
            )
    refund.status = target_status
    _sync_full_refund_cancellation(db, refund, payment, target_status)
    try:
        db.commit()
        db.refresh(refund)
        return refund
    except SQLAlchemyError as error:
        refund_id = refund.id
        db.rollback()
        persisted = db.get(Refund, refund_id)
        if persisted is not None and persisted.status == target_status:
            pending_cancellation = None
            if (
                target_status == PaymentRefundStatus.PROCESSED
                and persisted.amount == payment.amount
                and payment.appointment_id is not None
            ):
                pending_cancellation = db.scalar(
                    select(AppointmentCancellation.id)
                    .where(
                        AppointmentCancellation.appointment_id
                        == payment.appointment_id,
                        AppointmentCancellation.refund_status
                        == AppointmentCancellationRefundStatus.PENDING,
                    )
                    .limit(1)
                )
            if pending_cancellation is None:
                return persisted
        raise RefundPersistenceError(
            "Unable to confirm reconciled refund state"
        ) from error


def _sync_full_refund_cancellation(
    db: Session,
    refund: Refund,
    payment: Payment,
    provider_status: PaymentRefundStatus,
) -> None:
    if (
        provider_status != PaymentRefundStatus.PROCESSED
        or refund.amount != payment.amount
        or payment.appointment_id is None
    ):
        return

    cancellations = db.scalars(
        select(AppointmentCancellation)
        .where(
            AppointmentCancellation.appointment_id == payment.appointment_id,
            AppointmentCancellation.refund_status
            == AppointmentCancellationRefundStatus.PENDING,
        )
        .with_for_update()
    ).all()
    for cancellation in cancellations:
        cancellation.refund_status = AppointmentCancellationRefundStatus.REFUNDED


def _log_admin_refund_reconciliation(
    actor_id: UUID | None,
    refund_id: UUID,
    previous_status: PaymentRefundStatus | None,
    resulting_status: PaymentRefundStatus | None,
    outcome: str,
) -> None:
    if actor_id is None:
        return
    logger.info(
        "Admin refund reconciliation actor_id=%s refund_id=%s previous_status=%s "
        "resulting_status=%s outcome=%s",
        actor_id,
        refund_id,
        previous_status.value if previous_status is not None else "unknown",
        resulting_status.value if resulting_status is not None else "unknown",
        outcome,
    )


def _recover_missing_provider_refund_id(
    db: Session,
    refund: Refund,
    payment: Payment,
    provider: RazorpayService,
    *,
    actor_id: UUID | None,
    previous_status: PaymentRefundStatus,
) -> PaymentRefundStatus | RefundReconciliationOutcome:
    try:
        payment_evidence = provider.fetch_payment(payment.provider_payment_id)
    except RazorpayIntegrationError as error:
        return _unchanged_refund_outcome(
            db,
            refund.id,
            previous_status,
            actor_id,
            "provider_unavailable",
            failure_classification=getattr(
                error, "failure_classification", "provider_unavailable"
            ),
            error=error,
        )
    payment_failure = _refund_payment_evidence_failure(
        payment_evidence, payment, allow_fully_refunded=True
    )
    if payment_failure is not None:
        return _unchanged_refund_outcome(
            db,
            refund.id,
            previous_status,
            actor_id,
            "evidence_conflict",
            failure_classification=payment_failure,
        )

    try:
        provider_refund_id, listed_status = _find_provider_refund_id(
            provider, payment, refund
        )
    except RefundHistoryNoMatchError as error:
        return _unchanged_refund_outcome(
            db,
            refund.id,
            previous_status,
            actor_id,
            "no_matching_refund",
            failure_classification=error.failure_classification
            if error.failure_classification != "evidence_unverifiable"
            else "provider_refund_not_found",
        )
    except RefundHistoryAmbiguousError:
        return _unchanged_refund_outcome(
            db,
            refund.id,
            previous_status,
            actor_id,
            "multiple_matching_refunds",
            failure_classification="provider_refund_ambiguous",
        )
    except RefundHistoryInvalidError:
        return _unchanged_refund_outcome(
            db,
            refund.id,
            previous_status,
            actor_id,
            "evidence_conflict",
            failure_classification="provider_refund_history_invalid",
        )
    except RazorpayIntegrationError as error:
        return _unchanged_refund_outcome(
            db,
            refund.id,
            previous_status,
            actor_id,
            "provider_unavailable",
            failure_classification=getattr(
                error, "failure_classification", "provider_unavailable"
            ),
            error=error,
        )

    refund.razorpay_refund_id = provider_refund_id
    try:
        refund_evidence = provider.fetch_refund(
            payment.provider_payment_id, provider_refund_id
        )
        _, verified_status = _refund_provider_status(refund_evidence, refund, payment)
    except RazorpayIntegrationError as error:
        return _unchanged_refund_outcome(
            db,
            refund.id,
            previous_status,
            actor_id,
            "provider_unavailable",
            failure_classification=getattr(
                error, "failure_classification", "provider_unavailable"
            ),
            error=error,
        )
    except RefundOutcomeUnknownError as error:
        return _unchanged_refund_outcome(
            db,
            refund.id,
            previous_status,
            actor_id,
            "evidence_conflict",
            failure_classification=error.failure_classification,
            error=error,
        )

    if verified_status != listed_status or (
        verified_status == PaymentRefundStatus.PROCESSED
        and not _refund_payment_evidence(
            payment_evidence,
            payment,
            refund.amount,
            allow_fully_refunded=verified_status == PaymentRefundStatus.PROCESSED
            and refund.amount == payment.amount,
        )
    ):
        evidence_failure = _refund_payment_evidence_failure(
            payment_evidence,
            payment,
            refund.amount,
            allow_fully_refunded=verified_status == PaymentRefundStatus.PROCESSED
            and refund.amount == payment.amount,
        )
        return _unchanged_refund_outcome(
            db,
            refund.id,
            previous_status,
            actor_id,
            "evidence_conflict",
            failure_classification=(
                "refund_status_conflicts_with_history"
                if verified_status != listed_status
                else evidence_failure or "refund_payment_totals_unverified"
            ),
        )
    if (
        payment_evidence.get("status") == "refunded"
        and verified_status != PaymentRefundStatus.PROCESSED
    ):
        return _unchanged_refund_outcome(
            db,
            refund.id,
            previous_status,
            actor_id,
            "evidence_conflict",
            failure_classification="provider_payment_refund_status_conflict",
        )
    return verified_status


def _reconcile_processing_refund(
    db: Session,
    refund_id: UUID,
    *,
    actor_id: UUID | None,
    recover_missing_provider_refund_id: bool = False,
    razorpay_service: RazorpayService | None = None,
) -> RefundReconciliationOutcome:
    provider = razorpay_service or RazorpayService()
    previous_status: PaymentRefundStatus | None = None
    try:
        payment_id = db.scalar(select(Refund.payment_id).where(Refund.id == refund_id))
        if payment_id is None:
            raise RefundNotFoundError("Refund was not found")
        payment = db.scalar(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        refund = db.scalar(
            select(Refund).where(Refund.id == refund_id).with_for_update()
        )
        if refund is None:
            raise RefundNotFoundError("Refund was not found")
        previous_status = refund.status
        if refund.payment_id != payment_id:
            raise RefundConflictError("Refund payment link changed during verification")
        if (
            payment is None
            or payment.provider != PaymentProvider.RAZORPAY
            or not payment.provider_payment_id
            or not payment.provider_order_id
        ):
            raise RefundValidationError(
                "Refund has no consistent Razorpay payment link"
            )
        if not refund.razorpay_refund_id and not recover_missing_provider_refund_id:
            raise RefundValidationError(
                "Refund has no stored Razorpay refund ID; manual investigation is required"
            )
        if not refund.razorpay_refund_id:
            if refund.status != PaymentRefundStatus.PROCESSING:
                raise RefundValidationError(
                    "Refund has no stored Razorpay refund ID; manual investigation is required"
                )
            recovery = _recover_missing_provider_refund_id(
                db,
                refund,
                payment,
                provider,
                actor_id=actor_id,
                previous_status=previous_status,
            )
            if isinstance(recovery, RefundReconciliationOutcome):
                return recovery
            target_status = recovery
        elif len(refund.razorpay_refund_id) > 255:
            raise RefundValidationError("Stored Razorpay refund ID is invalid")
        else:
            refund_evidence = provider.fetch_refund(
                payment.provider_payment_id, refund.razorpay_refund_id
            )
            _, target_status = _refund_provider_status(refund_evidence, refund, payment)
            payment_evidence = provider.fetch_payment(payment.provider_payment_id)
            payment_failure = _refund_payment_evidence_failure(
                payment_evidence,
                payment,
                allow_fully_refunded=(
                    target_status == PaymentRefundStatus.PROCESSED
                    and refund.amount == payment.amount
                ),
            )
            if payment_failure is not None:
                raise RefundOutcomeUnknownError(
                    "Razorpay payment evidence could not reconcile this refund",
                    failure_classification=payment_failure,
                )
            refund_total_failure = (
                _refund_payment_evidence_failure(
                    payment_evidence,
                    payment,
                    refund.amount,
                    allow_fully_refunded=(
                        target_status == PaymentRefundStatus.PROCESSED
                        and refund.amount == payment.amount
                    ),
                )
                if target_status == PaymentRefundStatus.PROCESSED
                else None
            )
            if refund_total_failure is not None:
                raise RefundOutcomeUnknownError(
                    "Razorpay payment totals do not confirm the processed refund",
                    failure_classification=refund_total_failure,
                )
        reconciled = _persist_reconciled_status(db, refund, payment, target_status)
        outcome = "updated" if previous_status != reconciled.status else "unchanged"
        _log_admin_refund_reconciliation(
            actor_id,
            refund_id,
            previous_status,
            reconciled.status,
            outcome,
        )
        return RefundReconciliationOutcome(reconciled, previous_status, outcome)
    except RefundNotFoundError:
        _log_admin_refund_reconciliation(
            actor_id, refund_id, previous_status, None, "not_found"
        )
        db.rollback()
        raise
    except RefundValidationError:
        _log_admin_refund_reconciliation(
            actor_id,
            refund_id,
            previous_status,
            previous_status,
            "manual_investigation",
        )
        db.rollback()
        raise
    except RefundConflictError:
        _log_admin_refund_reconciliation(
            actor_id, refund_id, previous_status, previous_status, "conflict"
        )
        db.rollback()
        raise
    except RefundOutcomeUnknownError:
        _log_admin_refund_reconciliation(
            actor_id,
            refund_id,
            previous_status,
            previous_status,
            "unverified_provider_evidence",
        )
        db.rollback()
        raise
    except RazorpayIntegrationError:
        _log_admin_refund_reconciliation(
            actor_id,
            refund_id,
            previous_status,
            previous_status,
            "provider_lookup_failed",
        )
        db.rollback()
        raise
    except RefundPersistenceError:
        _log_admin_refund_reconciliation(
            actor_id,
            refund_id,
            previous_status,
            previous_status,
            "persistence_failed",
        )
        db.rollback()
        raise
    except Exception:
        _log_admin_refund_reconciliation(
            actor_id, refund_id, previous_status, previous_status, "failed"
        )
        db.rollback()
        raise


def reconcile_processing_refund(
    db: Session,
    refund_id: UUID,
    *,
    razorpay_service: RazorpayService | None = None,
) -> Refund:
    outcome = _reconcile_processing_refund(
        db,
        refund_id,
        actor_id=None,
        razorpay_service=razorpay_service,
    )
    return outcome.refund


def reconcile_refund_for_admin(
    db: Session,
    refund_id: UUID,
    *,
    actor_id: UUID,
    razorpay_service: RazorpayService | None = None,
) -> RefundReconciliationOutcome:
    return _reconcile_processing_refund(
        db,
        refund_id,
        actor_id=actor_id,
        recover_missing_provider_refund_id=True,
        razorpay_service=razorpay_service,
    )


def _webhook_refund_entity(payload: dict) -> tuple[dict | None, dict | None]:
    payload_data = payload.get("payload")
    if not isinstance(payload_data, dict):
        return None, None
    refund_data = payload_data.get("refund")
    payment_data = payload_data.get("payment")
    refund_entity = refund_data.get("entity") if isinstance(refund_data, dict) else None
    payment_entity = (
        payment_data.get("entity") if isinstance(payment_data, dict) else None
    )
    if not isinstance(refund_entity, dict) or not isinstance(payment_entity, dict):
        return None, None
    return refund_entity, payment_entity


def _finish_refund_webhook(
    event: PaymentWebhookEvent,
    status: PaymentWebhookEventStatus,
    error_message: str | None = None,
) -> None:
    from datetime import UTC, datetime

    event.status = status
    event.error_message = error_message
    event.processed_at = datetime.now(UTC)


def process_refund_webhook(
    db: Session,
    event: PaymentWebhookEvent,
    event_type: str,
    payload: dict,
    provider: RazorpayService,
) -> PaymentWebhookEventStatus:
    refund_entity, payment_entity = _webhook_refund_entity(payload)
    if refund_entity is None or payment_entity is None:
        _finish_refund_webhook(
            event,
            PaymentWebhookEventStatus.FAILED,
            "Refund webhook entities are missing or invalid",
        )
        db.commit()
        return event.status

    provider_refund_id = refund_entity.get("id")
    provider_payment_id = payment_entity.get("id")
    if (
        not isinstance(provider_refund_id, str)
        or not provider_refund_id
        or len(provider_refund_id) > 255
        or not isinstance(provider_payment_id, str)
        or not provider_payment_id
        or len(provider_payment_id) > 255
    ):
        _finish_refund_webhook(
            event,
            PaymentWebhookEventStatus.FAILED,
            "Refund webhook identifiers are invalid",
        )
        db.commit()
        return event.status

    if event.status == PaymentWebhookEventStatus.RETRYABLE and (
        event.event_type != event_type
        or event.provider_refund_id != provider_refund_id
        or event.provider_payment_id != provider_payment_id
    ):
        return event.status

    event.event_type = event_type
    event.provider_refund_id = provider_refund_id
    event.provider_payment_id = provider_payment_id
    order_id = payment_entity.get("order_id")
    event.provider_order_id = (
        order_id if isinstance(order_id, str) and len(order_id) <= 255 else None
    )

    payment = db.scalar(
        select(Payment)
        .where(Payment.provider_payment_id == provider_payment_id)
        .with_for_update()
    )
    if (
        payment is None
        or payment.provider != PaymentProvider.RAZORPAY
        or not payment.provider_order_id
        or (event.provider_order_id and payment.provider_order_id != order_id)
        or payment_entity.get("status") != "captured"
        or type(payment_entity.get("amount")) is not int
        or payment_entity.get("amount") != payment.amount
        or payment_entity.get("currency") != payment.currency
    ):
        _finish_refund_webhook(
            event,
            PaymentWebhookEventStatus.FAILED,
            "Refund webhook payment does not match the local payment",
        )
        db.commit()
        return event.status

    refund_amount = refund_entity.get("amount")
    refund_currency = refund_entity.get("currency")
    if (
        refund_entity.get("entity") != "refund"
        or refund_entity.get("payment_id") != provider_payment_id
        or type(refund_amount) is not int
        or refund_amount <= 0
        or refund_currency != payment.currency
    ):
        _finish_refund_webhook(
            event,
            PaymentWebhookEventStatus.FAILED,
            "Refund webhook details do not match the local payment",
        )
        db.commit()
        return event.status

    try:
        payment_evidence = provider.fetch_payment(provider_payment_id)
    except RazorpayIntegrationError:
        _finish_refund_webhook(
            event,
            PaymentWebhookEventStatus.RETRYABLE,
            "Razorpay payment lookup failed while processing refund event",
        )
        db.commit()
        return event.status
    if not _refund_payment_evidence(
        payment_evidence, payment, allow_fully_refunded=True
    ):
        _finish_refund_webhook(
            event,
            PaymentWebhookEventStatus.FAILED,
            "Razorpay payment evidence does not match the webhook",
        )
        db.commit()
        return event.status

    try:
        refund_evidence = provider.fetch_refund(provider_payment_id, provider_refund_id)
    except RazorpayIntegrationError:
        _finish_refund_webhook(
            event,
            PaymentWebhookEventStatus.RETRYABLE,
            "Razorpay refund lookup failed while processing refund event",
        )
        db.commit()
        return event.status
    evidence_id = (
        refund_evidence.get("id") if isinstance(refund_evidence, dict) else None
    )
    local_refund = db.scalar(
        select(Refund)
        .where(Refund.razorpay_refund_id == provider_refund_id)
        .with_for_update()
    )
    if (
        local_refund is None
        or local_refund.payment_id != payment.id
        or evidence_id != provider_refund_id
        or local_refund.amount != refund_amount
        or local_refund.currency != refund_currency
    ):
        _finish_refund_webhook(
            event,
            PaymentWebhookEventStatus.FAILED,
            "No matching persisted refund intent was found",
        )
        db.commit()
        return event.status

    try:
        _, provider_status = _refund_provider_status(
            refund_evidence, local_refund, payment
        )
    except RefundOutcomeUnknownError as error:
        _finish_refund_webhook(event, PaymentWebhookEventStatus.FAILED, str(error))
        db.commit()
        return event.status

    if (
        provider_status == PaymentRefundStatus.PROCESSED
        and not _refund_payment_evidence(
            payment_evidence,
            payment,
            local_refund.amount,
            allow_fully_refunded=local_refund.amount == payment.amount,
        )
    ):
        _finish_refund_webhook(
            event,
            PaymentWebhookEventStatus.RETRYABLE,
            "Razorpay payment totals do not yet confirm the processed refund",
        )
        db.commit()
        return event.status
    if (
        isinstance(payment_evidence, dict)
        and payment_evidence.get("status") == "refunded"
        and provider_status != PaymentRefundStatus.PROCESSED
    ):
        _finish_refund_webhook(
            event,
            PaymentWebhookEventStatus.FAILED,
            "Refund status conflicts with the fully refunded payment",
        )
        db.commit()
        return event.status

    if (
        local_refund.status
        in {
            PaymentRefundStatus.PROCESSED,
            PaymentRefundStatus.FAILED,
        }
        and local_refund.status != provider_status
    ):
        _finish_refund_webhook(
            event,
            PaymentWebhookEventStatus.FAILED,
            "Provider refund state conflicts with a terminal local state",
        )
        db.commit()
        return event.status

    local_refund.status = provider_status
    _sync_full_refund_cancellation(db, local_refund, payment, provider_status)
    _finish_refund_webhook(event, PaymentWebhookEventStatus.PROCESSED)
    db.commit()
    return event.status


def create_full_refund(
    db: Session,
    payment_id: UUID,
    idempotency_key: str,
    reason: str,
    *,
    razorpay_service: RazorpayService | None = None,
) -> Refund:
    if not _IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key):
        raise RefundValidationError("A valid idempotency key is required")
    if not reason.strip():
        raise RefundValidationError("A refund reason is required")

    try:
        payment = _load_locked_payment(db, payment_id)
        if payment is None:
            raise RefundNotFoundError("Payment was not found")

        existing = _return_existing_refund(
            _load_refund_by_key(db, idempotency_key),
            payment.id,
        )
        if existing is not None:
            existing_id = existing.id
            db.rollback()
            persisted = db.get(Refund, existing_id)
            if persisted is None:
                raise RefundPersistenceError(
                    "Previously persisted refund could not be reloaded"
                )
            return persisted

        provider = razorpay_service or RazorpayService()
        captured_amount, provider_amount_refunded = _verify_captured_payment(
            payment, provider
        )
        processed_amount, reserved_amount = _reserved_amounts(db, payment.id)
        amount_already_accounted = (
            max(provider_amount_refunded, processed_amount) + reserved_amount
        )
        if amount_already_accounted + captured_amount > captured_amount:
            raise RefundConflictError(
                "Payment already has a refund or an unresolved refund reservation"
            )

        provider_payment_id = payment.provider_payment_id
        currency = payment.currency
        refund = _persist_intent(db, payment, captured_amount, idempotency_key, reason)
    except (RefundValidationError, RefundConflictError, RefundNotFoundError):
        db.rollback()
        raise
    except SQLAlchemyError as error:
        db.rollback()
        raise RefundPersistenceError("Unable to prepare refund") from error
    except Exception:
        db.rollback()
        raise

    try:
        logger.info(
            "Submitting refund to Razorpay",
            extra={
                "refund_event": "submission_started",
                "refund_id": str(refund.id),
                "payment_id": str(payment_id),
                "amount": captured_amount,
                "currency": currency,
                "provider_refund_id_returned": False,
            },
        )
        result = provider.create_full_refund(
            provider_payment_id, captured_amount, idempotency_key
        )
    except RazorpayRefundRejectedError:
        logger.warning(
            "Razorpay definitively rejected refund",
            extra={
                "refund_event": "submission_failed",
                "refund_id": str(refund.id),
                "payment_id": str(payment_id),
                "amount": captured_amount,
                "currency": currency,
                "provider_refund_id_returned": False,
                "failure_classification": "definitive_rejection",
            },
        )
        _mark_definitive_failure(db, refund)
        raise
    except RazorpayRefundOutcomeUnknownError as error:
        logger.warning(
            "Razorpay refund outcome is uncertain",
            extra={
                "refund_event": "submission_failed",
                "refund_id": str(refund.id),
                "payment_id": str(payment_id),
                "amount": captured_amount,
                "currency": currency,
                "provider_refund_id_returned": False,
                "failure_classification": error.failure_classification,
            },
        )
        raise RefundOutcomeUnknownError(
            "Razorpay refund may have succeeded; reconciliation is required"
        ) from error
    except RazorpayRefundNotSubmittedError:
        logger.warning(
            "Razorpay refund was not submitted",
            extra={
                "refund_event": "submission_failed",
                "refund_id": str(refund.id),
                "payment_id": str(payment_id),
                "amount": captured_amount,
                "currency": currency,
                "provider_refund_id_returned": False,
                "failure_classification": "not_submitted",
            },
        )
        raise
    except RazorpayIntegrationError:
        logger.warning(
            "Razorpay refund outcome could not be confirmed",
            extra={
                "refund_event": "submission_failed",
                "refund_id": str(refund.id),
                "payment_id": str(payment_id),
                "amount": captured_amount,
                "currency": currency,
                "provider_refund_id_returned": False,
                "failure_classification": "provider_error",
            },
        )
        raise RefundOutcomeUnknownError(
            "Razorpay refund outcome could not be confirmed; reconciliation is required"
        ) from None

    provider_status = result.get("status") if isinstance(result, dict) else None
    provider_refund_id_returned = bool(
        isinstance(result, dict) and isinstance(result.get("id"), str) and result["id"]
    )
    logger.info(
        "Razorpay refund response received",
        extra={
            "refund_event": "provider_response_received",
            "refund_id": str(refund.id),
            "payment_id": str(payment_id),
            "amount": captured_amount,
            "currency": currency,
            "provider_response_status": (
                provider_status if isinstance(provider_status, str) else None
            ),
            "provider_http_status": None,
            "provider_refund_id_returned": provider_refund_id_returned,
        },
    )

    try:
        provider_refund_id, refund_status = _provider_result_status(
            result, provider_payment_id, currency, captured_amount
        )
    except RefundOutcomeUnknownError:
        logger.error(
            "Razorpay returned an unverifiable refund response",
            extra={
                "refund_event": "provider_response_unverifiable",
                "refund_id": str(refund.id),
                "payment_id": str(payment_id),
                "amount": captured_amount,
                "currency": currency,
                "provider_response_status": (
                    provider_status if isinstance(provider_status, str) else None
                ),
                "provider_refund_id_returned": provider_refund_id_returned,
                "failure_classification": "unverifiable_provider_response",
            },
        )
        raise

    persisted = _persist_provider_result(db, refund, provider_refund_id, refund_status)
    logger.info(
        "Razorpay refund result persisted",
        extra={
            "refund_event": "provider_result_persisted",
            "refund_id": str(persisted.id),
            "payment_id": str(persisted.payment_id),
            "amount": persisted.amount,
            "currency": persisted.currency,
            "provider_response_status": refund_status.value,
            "provider_refund_id_returned": bool(persisted.razorpay_refund_id),
        },
    )
    return persisted
