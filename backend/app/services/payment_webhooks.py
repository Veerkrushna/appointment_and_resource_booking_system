import math
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.booking_hold import BookingHoldStatus
from app.models.payment import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    PaymentWebhookCaptureValidationFailure,
    PaymentWebhookEvent,
    PaymentWebhookEventStatus,
)
from app.models.user import User
from app.services.booking import (
    BookingConflictError,
    BookingValidationError,
    _lock_provider_and_get_service,
    _validate_slot,
)
from app.services.payment_orders import (
    _ensure_no_active_hold,
)
from app.services.payment_refunds import process_refund_webhook
from app.services.payment_verification import (
    PaymentStateConflictError,
    _build_held_appointment,
    _load_payment_hold,
    _notify_after_commit,
)


def _captured_entity(payload: dict) -> dict | None:
    event_payload = payload.get("payload")
    if not isinstance(event_payload, dict):
        return None
    payment_object = event_payload.get("payment")
    if not isinstance(payment_object, dict):
        return None
    entity = payment_object.get("entity")
    return entity if isinstance(entity, dict) else None


def _finish_event(
    event: PaymentWebhookEvent,
    status: PaymentWebhookEventStatus,
    *,
    error_message: str | None = None,
) -> None:
    event.status = status
    event.error_message = error_message
    event.processed_at = datetime.now(UTC)


def _persist_external_capture(payment: Payment, provider_payment_id: str) -> None:
    payment.status = PaymentStatus.CAPTURED
    if payment.provider_payment_id is None:
        payment.provider_payment_id = provider_payment_id


def _capture_observation_value(value: object) -> object:
    if value is None or type(value) is bool:
        return value
    if type(value) is int and abs(value) <= (2**53 - 1):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, str):
        return value[:255]
    return {"type": type(value).__name__}


def _record_capture_validation_failure(
    event: PaymentWebhookEvent,
    entity: dict,
    failure: PaymentWebhookCaptureValidationFailure,
) -> None:
    event.capture_validation_failure = failure.value
    event.capture_validation_details = {
        key: _capture_observation_value(entity[key])
        for key in ("id", "order_id", "status", "captured", "amount", "currency")
        if key in entity
    }


def _recover_verified_capture(
    db: Session,
    provider_event_id: str,
    event_type: str,
    provider_order_id: str,
    provider_payment_id: str,
    amount: int,
    currency: str,
) -> PaymentWebhookEventStatus:
    try:
        event = db.scalar(
            select(PaymentWebhookEvent)
            .where(PaymentWebhookEvent.provider_event_id == provider_event_id)
            .with_for_update()
        )
        payment = db.scalar(
            select(Payment)
            .where(Payment.provider_order_id == provider_order_id)
            .with_for_update()
        )
        if (
            payment is None
            or payment.provider != PaymentProvider.RAZORPAY
            or payment.provider_order_id != provider_order_id
            or payment.amount != amount
            or payment.currency != currency
            or payment.provider_payment_id not in (None, provider_payment_id)
        ):
            return (
                event.status
                if event is not None
                else PaymentWebhookEventStatus.RECEIVED
            )

        if event is not None:
            if event.status == PaymentWebhookEventStatus.PROCESSED:
                if (
                    payment.status == PaymentStatus.CAPTURED
                    and payment.provider_payment_id == provider_payment_id
                    and payment.appointment_id is not None
                    and db.get(Appointment, payment.appointment_id) is not None
                ):
                    return event.status
                return event.status
            if event.status not in {
                PaymentWebhookEventStatus.RECEIVED,
                PaymentWebhookEventStatus.RETRYABLE,
            }:
                return event.status
            if (
                event.event_type != event_type
                or event.provider_order_id != provider_order_id
                or event.provider_payment_id != provider_payment_id
            ):
                return event.status

        if payment.status not in {
            PaymentStatus.CREATED,
            PaymentStatus.PENDING,
            PaymentStatus.CAPTURED,
        }:
            return (
                event.status if event is not None else PaymentWebhookEventStatus.FAILED
            )

        if payment.appointment_id is not None:
            if (
                payment.status == PaymentStatus.CAPTURED
                and payment.provider_payment_id == provider_payment_id
                and db.get(Appointment, payment.appointment_id) is not None
            ):
                if event is None:
                    event = PaymentWebhookEvent(
                        id=uuid4(),
                        provider_event_id=provider_event_id,
                        event_type=event_type,
                        provider_order_id=provider_order_id,
                        provider_payment_id=provider_payment_id,
                        status=PaymentWebhookEventStatus.RECEIVED,
                    )
                    db.add(event)
                _finish_event(event, PaymentWebhookEventStatus.PROCESSED)
                db.commit()
                return event.status
            return (
                event.status if event is not None else PaymentWebhookEventStatus.FAILED
            )

        if event is None:
            event = PaymentWebhookEvent(
                id=uuid4(),
                provider_event_id=provider_event_id,
                event_type=event_type,
                provider_order_id=provider_order_id,
                provider_payment_id=provider_payment_id,
                status=PaymentWebhookEventStatus.RETRYABLE,
            )
            db.add(event)
        else:
            event.event_type = event_type
            event.provider_order_id = provider_order_id
            event.provider_payment_id = provider_payment_id

        payment.status = PaymentStatus.CAPTURED
        payment.provider_payment_id = provider_payment_id
        _finish_event(
            event,
            PaymentWebhookEventStatus.RETRYABLE,
            error_message="Verified capture was saved; fulfillment will be retried",
        )
        db.commit()
        return event.status
    except Exception:
        db.rollback()
        raise


def process_payment_webhook(
    db: Session,
    provider_event_id: str,
    event_type: str,
    payload: dict,
    razorpay_service=None,
) -> PaymentWebhookEventStatus:
    appointment = None
    capture_verified = False
    try:
        db.execute(
            insert(PaymentWebhookEvent)
            .values(
                id=uuid4(),
                provider_event_id=provider_event_id,
                event_type=event_type,
                status=PaymentWebhookEventStatus.RECEIVED,
            )
            .on_conflict_do_nothing(
                index_elements=[PaymentWebhookEvent.provider_event_id]
            )
        )
        event = db.scalar(
            select(PaymentWebhookEvent)
            .where(PaymentWebhookEvent.provider_event_id == provider_event_id)
            .with_for_update()
        )
        if event is None:
            raise RuntimeError("Unable to create webhook event record")

        if event.status not in {
            PaymentWebhookEventStatus.RECEIVED,
            PaymentWebhookEventStatus.RETRYABLE,
        }:
            return event.status

        retrying = event.status == PaymentWebhookEventStatus.RETRYABLE
        if not retrying:
            event.event_type = event_type
        if event_type in {
            "refund.created",
            "refund.processed",
            "refund.failed",
        }:
            from app.services.razorpay import RazorpayService

            return process_refund_webhook(
                db,
                event,
                event_type,
                payload,
                razorpay_service or RazorpayService(),
            )

        event_entity = (
            _captured_entity(payload) if event_type == "payment.captured" else None
        )
        if event_entity is not None and not retrying:
            order_id = event_entity.get("order_id")
            event.provider_order_id = (
                order_id if isinstance(order_id, str) and len(order_id) <= 255 else None
            )
            payment_id = event_entity.get("id")
            event.provider_payment_id = (
                payment_id
                if isinstance(payment_id, str) and len(payment_id) <= 255
                else None
            )

        if retrying and (
            event_type != event.event_type
            or event_entity is None
            or event_entity.get("order_id") != event.provider_order_id
            or event_entity.get("id") != event.provider_payment_id
        ):
            return event.status

        if event_type != "payment.captured":
            _finish_event(event, PaymentWebhookEventStatus.IGNORED)
            db.commit()
            return event.status

        if event_entity is None:
            _finish_event(
                event,
                PaymentWebhookEventStatus.FAILED,
                error_message="Captured payment entity is missing or invalid",
            )
            db.commit()
            return event.status

        provider_order_id = event_entity.get("order_id")
        provider_payment_id = event_entity.get("id")
        payment = None
        if isinstance(provider_order_id, str) and provider_order_id:
            payment = db.scalar(
                select(Payment)
                .where(Payment.provider_order_id == provider_order_id)
                .with_for_update()
            )
        if payment is None:
            if (
                isinstance(provider_payment_id, str)
                and provider_payment_id
                and len(provider_payment_id) <= 255
            ):
                possible_matches = db.scalars(
                    select(Payment)
                    .where(Payment.provider_payment_id == provider_payment_id)
                    .with_for_update()
                    .limit(2)
                ).all()
                if (
                    len(possible_matches) == 1
                    and possible_matches[0].provider == PaymentProvider.RAZORPAY
                ):
                    _record_capture_validation_failure(
                        event,
                        event_entity,
                        PaymentWebhookCaptureValidationFailure.PROVIDER_ORDER_ID_MISMATCH,
                    )
                    _finish_event(
                        event,
                        PaymentWebhookEventStatus.FAILED,
                        error_message="Provider order ID conflicts with the local payment",
                    )
                    db.commit()
                    return event.status
            _finish_event(
                event,
                PaymentWebhookEventStatus.IGNORED,
                error_message="No local payment matches the provider order",
            )
            db.commit()
            return event.status

        if payment.provider != PaymentProvider.RAZORPAY:
            _finish_event(
                event,
                PaymentWebhookEventStatus.FAILED,
                error_message="Local payment provider does not match the webhook",
            )
            db.commit()
            return event.status

        valid_payment_id = (
            isinstance(provider_payment_id, str)
            and bool(provider_payment_id)
            and len(provider_payment_id) <= 255
        )
        captured = (
            event_entity.get("status") == "captured"
            and event_entity.get("captured") is True
        )
        if not valid_payment_id or not captured:
            failure = (
                PaymentWebhookCaptureValidationFailure.INVALID_PAYMENT_ID
                if not valid_payment_id
                else PaymentWebhookCaptureValidationFailure.INVALID_CAPTURE_STATUS
            )
            _record_capture_validation_failure(event, event_entity, failure)
            _finish_event(
                event,
                PaymentWebhookEventStatus.FAILED,
                error_message="Webhook payment identity or capture state is invalid",
            )
            db.commit()
            return event.status

        if (
            payment.provider_payment_id is not None
            and payment.provider_payment_id != provider_payment_id
        ):
            _record_capture_validation_failure(
                event,
                event_entity,
                PaymentWebhookCaptureValidationFailure.PROVIDER_PAYMENT_ID_MISMATCH,
            )
            _finish_event(
                event,
                PaymentWebhookEventStatus.FAILED,
                error_message="Provider payment ID conflicts with the local payment",
            )
            db.commit()
            return event.status

        amount = event_entity.get("amount")
        currency = event_entity.get("currency")
        amount_failure = (
            PaymentWebhookCaptureValidationFailure.INVALID_AMOUNT
            if isinstance(amount, bool) or not isinstance(amount, int)
            else (
                PaymentWebhookCaptureValidationFailure.AMOUNT_MISMATCH
                if amount != payment.amount
                else None
            )
        )
        if amount_failure is not None or currency != payment.currency:
            failure = amount_failure or (
                PaymentWebhookCaptureValidationFailure.CURRENCY_MISMATCH
            )
            _record_capture_validation_failure(event, event_entity, failure)
            _finish_event(
                event,
                PaymentWebhookEventStatus.FAILED,
                error_message="Captured amount or currency does not match the local payment",
            )
            db.commit()
            return event.status

        capture_verified = True

        if payment.status == PaymentStatus.CAPTURED and payment.appointment_id:
            appointment_exists = db.get(Appointment, payment.appointment_id) is not None
            if (
                appointment_exists
                and payment.provider_payment_id == provider_payment_id
            ):
                _finish_event(event, PaymentWebhookEventStatus.PROCESSED)
            else:
                _finish_event(
                    event,
                    PaymentWebhookEventStatus.FAILED,
                    error_message="Captured payment is not consistently linked locally",
                )
            db.commit()
            return event.status

        if payment.status not in {
            PaymentStatus.CREATED,
            PaymentStatus.PENDING,
            PaymentStatus.CAPTURED,
        }:
            event.local_payment_state_conflict = True
            _finish_event(
                event,
                PaymentWebhookEventStatus.FAILED,
                error_message="Local payment state conflicts with provider capture",
            )
            db.commit()
            return event.status

        try:
            hold = _load_payment_hold(db, payment.id)
        except PaymentStateConflictError:
            _persist_external_capture(payment, provider_payment_id)
            _finish_event(
                event,
                PaymentWebhookEventStatus.FAILED,
                error_message="Captured payment has multiple booking holds",
            )
            db.commit()
            return event.status
        if hold is None or hold.customer_id != payment.customer_id:
            _persist_external_capture(payment, provider_payment_id)
            _finish_event(
                event,
                PaymentWebhookEventStatus.FAILED,
                error_message="Captured payment has no valid booking hold",
            )
            db.commit()
            return event.status
        if hold.status not in {
            BookingHoldStatus.ACTIVE,
            BookingHoldStatus.EXPIRED,
        }:
            _persist_external_capture(payment, provider_payment_id)
            _finish_event(
                event,
                PaymentWebhookEventStatus.FAILED,
                error_message="Captured payment booking hold is not active",
            )
            db.commit()
            return event.status

        now_utc = datetime.now(UTC)
        if hold.status == BookingHoldStatus.ACTIVE and hold.expires_at <= now_utc:
            hold.status = BookingHoldStatus.EXPIRED

        try:
            provider, service = _lock_provider_and_get_service(
                db, hold.provider_id, hold.service_id
            )
            start_utc, end_utc = _validate_slot(
                db,
                hold.appointment_start,
                service.duration_minutes,
                provider,
                buffer_time_minutes=service.buffer_time_minutes or 0,
            )
            if start_utc != hold.appointment_start or end_utc != hold.appointment_end:
                raise BookingValidationError(
                    "Held appointment no longer matches the service"
                )
            _ensure_no_active_hold(
                db,
                provider.id,
                start_utc,
                end_utc,
                service.buffer_time_minutes or 0,
                now_utc,
                exclude_hold_id=hold.id,
            )
        except BookingConflictError:
            _persist_external_capture(payment, provider_payment_id)
            _finish_event(
                event,
                PaymentWebhookEventStatus.RETRYABLE,
                error_message="Captured payment slot is temporarily unavailable",
            )
            db.commit()
            return event.status
        except BookingValidationError:
            _persist_external_capture(payment, provider_payment_id)
            _finish_event(
                event,
                PaymentWebhookEventStatus.FAILED,
                error_message="Captured payment slot could not be safely booked",
            )
            db.commit()
            return event.status

        customer = db.get(User, payment.customer_id)
        if customer is None:
            _persist_external_capture(payment, provider_payment_id)
            _finish_event(
                event,
                PaymentWebhookEventStatus.FAILED,
                error_message="Captured payment customer no longer exists",
            )
            db.commit()
            return event.status

        appointment = _build_held_appointment(
            customer, hold, service, start_utc, end_utc
        )
        db.add(appointment)
        db.flush()
        payment.status = PaymentStatus.CAPTURED
        payment.provider_payment_id = provider_payment_id
        payment.provider_signature = None
        payment.appointment_id = appointment.id
        hold.status = BookingHoldStatus.CONVERTED
        _finish_event(event, PaymentWebhookEventStatus.PROCESSED)
        # Razorpay capture is external; a failed transaction must be retried/reconciled.
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        if capture_verified:
            recovered_status = _recover_verified_capture(
                db,
                provider_event_id,
                event_type,
                provider_order_id,
                provider_payment_id,
                amount,
                currency,
            )
            if recovered_status == PaymentWebhookEventStatus.PROCESSED:
                return recovered_status
        raise
    except Exception:
        db.rollback()
        raise

    if appointment is not None:
        _notify_after_commit(appointment)
    return PaymentWebhookEventStatus.PROCESSED
