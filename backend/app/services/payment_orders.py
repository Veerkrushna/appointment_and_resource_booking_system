from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.booking_hold import BookingHold, BookingHoldStatus
from app.models.payment import Payment, PaymentProvider, PaymentStatus
from app.models.service import Service
from app.models.user import User
from app.schemas.payment import AppointmentPaymentOrderCreate
from app.services.booking import (
    BookingConflictError,
    BookingValidationError,
    _lock_provider_and_get_service,
    _validate_slot,
)
from app.services.razorpay import RazorpayIntegrationError, RazorpayService

PAYMENT_CURRENCY = "INR"


def _amount_in_paise(price: Decimal | None) -> int:
    if price is None:
        raise BookingValidationError("Service price is not configured")

    amount = price * 100
    if amount <= 0 or amount != amount.to_integral_value():
        raise BookingValidationError("Service price must be a positive amount in paise")
    return int(amount)


def _ensure_no_active_hold(
    db: Session,
    provider_id,
    start_utc: datetime,
    end_utc: datetime,
    buffer_time_minutes: int,
    now_utc: datetime,
    exclude_hold_id=None,
) -> None:
    requested_blocked_end = end_utc + timedelta(minutes=buffer_time_minutes)
    held_blocked_end = BookingHold.appointment_end + (
        func.coalesce(Service.buffer_time_minutes, 0)
        * literal_column("INTERVAL '1 minute'")
    )
    query = (
        select(BookingHold.id)
        .join(Service, Service.id == BookingHold.service_id)
        .where(
            BookingHold.provider_id == provider_id,
            BookingHold.status == BookingHoldStatus.ACTIVE,
            BookingHold.expires_at > now_utc,
            BookingHold.appointment_start < requested_blocked_end,
            held_blocked_end > start_utc,
        )
        .limit(1)
    )
    if exclude_hold_id is not None:
        query = query.where(BookingHold.id != exclude_hold_id)
    overlapping_hold = db.scalar(query)
    if overlapping_hold is not None:
        raise BookingConflictError("Appointment slot is already held")


def create_appointment_payment_order(
    db: Session,
    customer: User,
    payload: AppointmentPaymentOrderCreate,
) -> Payment:
    try:
        provider, service = _lock_provider_and_get_service(
            db, payload.provider_id, payload.service_id
        )
        start_utc, end_utc = _validate_slot(
            db,
            payload.appointment_start,
            service.duration_minutes,
            provider,
            buffer_time_minutes=service.buffer_time_minutes or 0,
        )

        now_utc = datetime.now(UTC)
        _ensure_no_active_hold(
            db,
            provider.id,
            start_utc,
            end_utc,
            service.buffer_time_minutes or 0,
            now_utc,
        )
        amount = _amount_in_paise(service.price)
        payment_id = uuid4()
        expires_at = now_utc + timedelta(minutes=settings.payment_hold_duration_minutes)
        payment = Payment(
            id=payment_id,
            customer_id=customer.id,
            amount=amount,
            currency=PAYMENT_CURRENCY,
            status=PaymentStatus.CREATED,
            provider=PaymentProvider.RAZORPAY,
            provider_order_id=None,
        )
        hold = BookingHold(
            customer_id=customer.id,
            service_id=service.id,
            provider_id=provider.id,
            user_name=payload.user_name,
            user_email=str(payload.user_email),
            user_phone=payload.user_phone,
            appointment_start=start_utc,
            appointment_end=end_utc,
            expires_at=expires_at,
            notes=payload.notes,
            status=BookingHoldStatus.ACTIVE,
            payment_id=payment_id,
        )
        db.add_all([payment, hold])
        db.flush()

        order = RazorpayService().create_order(
            amount=amount,
            currency=PAYMENT_CURRENCY,
            receipt=str(payment_id),
        )
        provider_order_id = order.get("id")
        if (
            not isinstance(provider_order_id, str)
            or not provider_order_id
            or len(provider_order_id) > 255
        ):
            raise RazorpayIntegrationError("Razorpay returned an invalid order ID")

        payment.provider_order_id = provider_order_id
        hold.expires_at = datetime.now(UTC) + timedelta(
            minutes=settings.payment_hold_duration_minutes
        )
        db.commit()
        db.refresh(payment)
        return payment
    except Exception:
        db.rollback()
        raise
