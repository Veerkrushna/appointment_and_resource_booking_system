from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.booking_hold import BookingHoldStatus
from app.models.payment import (
    Payment,
    PaymentProvider,
    PaymentStatus,
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


def process_payment_webhook(
    db: Session,
    provider_event_id: str,
    event_type: str,
    payload: dict,
) -> PaymentWebhookEventStatus:
    appointment = None
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

        if event.status != PaymentWebhookEventStatus.RECEIVED:
            return event.status

        event.event_type = event_type
        event_entity = (
            _captured_entity(payload) if event_type == "payment.captured" else None
        )
        if event_entity is not None:
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
            _persist_external_capture(payment, provider_payment_id)
            _finish_event(
                event,
                PaymentWebhookEventStatus.FAILED,
                error_message="Provider payment ID conflicts with the local payment",
            )
            db.commit()
            return event.status

        amount = event_entity.get("amount")
        currency = event_entity.get("currency")
        if (
            isinstance(amount, bool)
            or not isinstance(amount, int)
            or amount != payment.amount
            or currency != payment.currency
        ):
            _persist_external_capture(payment, provider_payment_id)
            _finish_event(
                event,
                PaymentWebhookEventStatus.FAILED,
                error_message="Captured amount or currency does not match the local payment",
            )
            db.commit()
            return event.status

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
            _persist_external_capture(payment, provider_payment_id)
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
        if hold.status != BookingHoldStatus.ACTIVE:
            _persist_external_capture(payment, provider_payment_id)
            _finish_event(
                event,
                PaymentWebhookEventStatus.FAILED,
                error_message="Captured payment booking hold is not active",
            )
            db.commit()
            return event.status

        now_utc = datetime.now(UTC)
        if hold.expires_at <= now_utc:
            hold.status = BookingHoldStatus.EXPIRED
            _persist_external_capture(payment, provider_payment_id)
            _finish_event(
                event,
                PaymentWebhookEventStatus.FAILED,
                error_message="Captured payment booking hold has expired",
            )
            db.commit()
            return event.status

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
        except (BookingConflictError, BookingValidationError):
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
    except Exception:
        db.rollback()
        raise

    if appointment is not None:
        _notify_after_commit(appointment)
    return PaymentWebhookEventStatus.PROCESSED
