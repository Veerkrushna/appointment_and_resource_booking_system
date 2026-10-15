import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.models.appointment import Appointment, AppointmentStatus
from app.models.booking_hold import BookingHold, BookingHoldStatus
from app.models.payment import Payment, PaymentProvider, PaymentStatus
from app.models.service import Service
from app.models.user import User
from app.schemas.appointment import AppointmentCreate
from app.schemas.payment import PaymentVerificationRequest
from app.services.booking import (
    BookingValidationError,
    _build_appointment,
    _lock_provider_and_get_service,
    _validate_slot,
)
from app.services.payment_orders import _ensure_no_active_hold
from app.services.razorpay import RazorpayService
from app.tasks.notification_tasks import (
    enqueue_confirmation_notification,
    schedule_appointment_notifications,
)

logger = logging.getLogger(__name__)


class PaymentNotFoundError(LookupError):
    pass


class InvalidPaymentVerificationError(ValueError):
    pass


class PaymentStateConflictError(ValueError):
    pass


def _load_payment(db: Session, customer: User, payment_id: UUID) -> Payment | None:
    return db.scalar(
        select(Payment)
        .options(selectinload(Payment.appointment))
        .where(
            Payment.customer_id == customer.id,
            Payment.id == payment_id,
        )
        .with_for_update()
    )


def _load_payment_hold(db: Session, payment_id) -> BookingHold | None:
    holds = db.scalars(
        select(BookingHold)
        .where(BookingHold.payment_id == payment_id)
        .with_for_update()
    ).all()
    if len(holds) > 1:
        raise PaymentStateConflictError("Payment has multiple booking holds")
    return holds[0] if holds else None


def _build_held_appointment(
    customer: User,
    hold: BookingHold,
    service: Service,
    start_utc: datetime,
    end_utc: datetime,
) -> Appointment:
    payload = AppointmentCreate(
        service_id=service.id,
        provider_id=hold.provider_id,
        user_name=hold.user_name,
        user_email=hold.user_email,
        user_phone=hold.user_phone,
        appointment_start=start_utc,
        notes=hold.notes,
    )
    appointment = _build_appointment(
        payload,
        customer,
        service,
        start_utc,
        end_utc,
    )
    appointment.status = AppointmentStatus.CONFIRMED
    return appointment


def _appointment_matches_hold(
    payment: Payment,
    hold: BookingHold | None,
    appointment: Appointment | None,
) -> bool:
    return bool(
        hold is not None
        and appointment is not None
        and payment.status == PaymentStatus.CAPTURED
        and payment.provider_payment_id
        and payment.appointment_id == appointment.id
        and payment.series_id is None
        and hold.payment_id == payment.id
        and hold.customer_id == payment.customer_id
        and hold.status == BookingHoldStatus.CONVERTED
        and appointment.customer_id == payment.customer_id
        and appointment.service_id == hold.service_id
        and appointment.provider_id == hold.provider_id
    )


def _load_existing_appointment(db: Session, payment: Payment) -> Appointment | None:
    if payment.appointment_id is None:
        return None
    appointment = db.get(Appointment, payment.appointment_id)
    hold = _load_payment_hold(db, payment.id)
    if not _appointment_matches_hold(payment, hold, appointment):
        raise PaymentStateConflictError("Payment has an inconsistent appointment link")
    return appointment


def _persist_verified_capture(
    db: Session,
    customer: User,
    payment: Payment,
    provider_payment_id: str,
    signature: str,
) -> Payment:
    payment.status = PaymentStatus.CAPTURED
    payment.provider_payment_id = provider_payment_id
    payment.provider_signature = signature
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        persisted_payment = _load_payment(db, customer, payment.id)
        if (
            persisted_payment is None
            or persisted_payment.status != PaymentStatus.CAPTURED
            or persisted_payment.provider_payment_id != provider_payment_id
            or persisted_payment.provider_order_id != payment.provider_order_id
            or persisted_payment.amount != payment.amount
            or persisted_payment.currency != payment.currency
        ):
            raise
        return persisted_payment

    persisted_payment = _load_payment(db, customer, payment.id)
    if (
        persisted_payment is None
        or persisted_payment.status != PaymentStatus.CAPTURED
        or persisted_payment.provider_payment_id != provider_payment_id
    ):
        raise PaymentStateConflictError(
            "Verified capture could not be confirmed in local storage"
        )
    return persisted_payment


def _fulfill_captured_payment(
    db: Session, customer: User, payment: Payment
) -> tuple[Payment, Appointment, bool]:
    try:
        payment = _load_payment(db, customer, payment.id)
        if (
            payment is None
            or payment.provider != PaymentProvider.RAZORPAY
            or payment.status != PaymentStatus.CAPTURED
        ):
            raise PaymentStateConflictError(
                "Captured payment is no longer available for fulfillment"
            )

        if payment.appointment_id is not None:
            appointment = _load_existing_appointment(db, payment)
            if appointment is None:
                raise PaymentStateConflictError(
                    "Payment has an inconsistent appointment link"
                )
            return payment, appointment, False

        if payment.series_id is not None or not payment.provider_payment_id:
            raise PaymentStateConflictError(
                "Captured payment has inconsistent fulfillment evidence"
            )

        hold = _load_payment_hold(db, payment.id)
        if hold is None or hold.customer_id != customer.id:
            raise PaymentStateConflictError("Active booking hold was not found")
        if hold.status != BookingHoldStatus.ACTIVE:
            raise PaymentStateConflictError("Booking hold is no longer active")

        now_utc = datetime.now(UTC)
        if hold.expires_at <= now_utc:
            hold.status = BookingHoldStatus.EXPIRED
            db.commit()
            raise PaymentStateConflictError("Booking hold has expired")

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

        appointment = _build_held_appointment(
            customer, hold, service, start_utc, end_utc
        )
        db.add(appointment)
        db.flush()
        payment.appointment_id = appointment.id
        hold.status = BookingHoldStatus.CONVERTED
        try:
            db.commit()
        except SQLAlchemyError as error:
            db.rollback()
            persisted_payment = _load_payment(db, customer, payment.id)
            if persisted_payment is None or persisted_payment.appointment_id is None:
                raise
            persisted_appointment = _load_existing_appointment(db, persisted_payment)
            if persisted_appointment is None:
                raise PaymentStateConflictError(
                    "Payment has an inconsistent appointment link"
                ) from error
            return persisted_payment, persisted_appointment, True

        persisted_payment = _load_payment(db, customer, payment.id)
        if persisted_payment is None or persisted_payment.appointment is None:
            raise PaymentStateConflictError(
                "Fulfilled payment has no persisted appointment"
            )
        return persisted_payment, persisted_payment.appointment, True
    except Exception:
        db.rollback()
        raise


def _notify_after_commit(appointment: Appointment) -> None:
    try:
        enqueue_confirmation_notification(appointment)
    except Exception:
        logger.exception(
            "Unable to enqueue confirmation notification for appointment %s",
            appointment.id,
        )
    try:
        schedule_appointment_notifications(appointment)
    except Exception:
        logger.exception(
            "Unable to schedule notifications for appointment %s", appointment.id
        )


def verify_appointment_payment(
    db: Session,
    customer: User,
    payload: PaymentVerificationRequest,
) -> Payment:
    payment = _load_payment(db, customer, payload.payment_id)
    if payment is None or payment.provider != PaymentProvider.RAZORPAY:
        raise PaymentNotFoundError("Payment was not found")
    if not payment.provider_order_id:
        raise PaymentStateConflictError("Payment has no provider order ID")
    if payload.order_id != payment.provider_order_id:
        raise PaymentStateConflictError("Payment order ID does not match")
    if (
        payment.provider_payment_id is not None
        and payment.provider_payment_id != payload.provider_payment_id
    ):
        raise PaymentStateConflictError("Provider payment ID does not match")
    if payment.status not in {
        PaymentStatus.CREATED,
        PaymentStatus.PENDING,
        PaymentStatus.CAPTURED,
    }:
        raise PaymentStateConflictError(
            "Payment cannot be verified in its current state"
        )

    if payment.appointment_id is not None:
        appointment = _load_existing_appointment(db, payment)
        if appointment is None:
            raise PaymentStateConflictError(
                "Payment has an inconsistent appointment link"
            )
        return payment

    if payment.status == PaymentStatus.CAPTURED:
        if payment.provider_payment_id != payload.provider_payment_id:
            raise PaymentStateConflictError(
                "Captured payment does not match this verification request"
            )
    else:
        if not RazorpayService().verify_payment(
            payment.provider_order_id,
            payload.provider_payment_id,
            payload.signature,
            expected_amount=payment.amount,
            expected_currency=payment.currency,
        ):
            raise InvalidPaymentVerificationError(
                "Payment signature or status is invalid"
            )
        payment = _persist_verified_capture(
            db,
            customer,
            payment,
            payload.provider_payment_id,
            payload.signature,
        )

    payment, appointment, created = _fulfill_captured_payment(db, customer, payment)
    if created:
        _notify_after_commit(appointment)
    return payment
