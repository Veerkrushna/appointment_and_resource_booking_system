import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
import razorpay
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.models.appointment import Appointment, AppointmentStatus
from app.payments.models import Payment, PaymentStatus
from app.tasks.notification_tasks import (
    enqueue_confirmation_notification,
    schedule_appointment_notifications,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["Payments"])

PENDING_HOLD_MINUTES = 10


def get_razorpay_client() -> razorpay.Client:
    return razorpay.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
    )


class CreateOrderRequest(BaseModel):
    booking_id: UUID


class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    key_id: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class VerifyPaymentResponse(BaseModel):
    status: str
    message: str
    booking_id: UUID | None = None


class PayAtAppointmentRequest(BaseModel):
    booking_id: UUID


class PayAtAppointmentResponse(BaseModel):
    status: str
    message: str
    booking_id: UUID


def confirm_payment_and_booking(
    db: Session, payment: Payment, provider_payment_id: str
) -> None:
    """Idempotently transitions payment to PAID and booking to CONFIRMED."""
    if payment.status != PaymentStatus.PAID:
        payment.status = PaymentStatus.PAID
        payment.provider_payment_id = provider_payment_id

    booking = db.get(Appointment, payment.booking_id)
    if booking is not None:
        if booking.status != AppointmentStatus.CONFIRMED:
            booking.status = AppointmentStatus.CONFIRMED
            booking.confirmed_at = datetime.now(UTC)
            db.commit()
            try:
                enqueue_confirmation_notification(booking)
            except Exception as exc:
                logger.warning(
                    "Unable to enqueue confirmation notification for %s: %s",
                    booking.id,
                    exc,
                )
            try:
                schedule_appointment_notifications(booking)
            except Exception as exc:
                logger.warning(
                    "Unable to schedule appointment notifications for %s: %s",
                    booking.id,
                    exc,
                )
        else:
            db.commit()
    else:
        db.commit()


@router.post("/create-order", response_model=CreateOrderResponse)
def create_order(
    payload: CreateOrderRequest,
    db: Annotated[Session, Depends(get_db)],
):
    booking = db.get(Appointment, payload.booking_id)
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    if booking.status != AppointmentStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Booking is not in PENDING state (current: {booking.status.value})",
        )

    # Check 10-minute hold window
    now_utc = datetime.now(UTC)
    if booking.created_at is not None:
        booking_created_at = booking.created_at
        if booking_created_at.tzinfo is None:
            booking_created_at = booking_created_at.replace(tzinfo=UTC)
        if now_utc - booking_created_at > timedelta(minutes=PENDING_HOLD_MINUTES):
            booking.status = AppointmentStatus.CANCELLED
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Booking slot hold expired. Please select a slot again.",
            )

    # Amount in paise (1 INR = 100 paise)
    service = booking.service
    if service is not None and service.price is not None and service.price > 0:
        amount_paise = int(service.price * 100)
    else:
        amount_paise = 50000  # Default demo amount: ₹500 (50,000 paise)

    currency = "INR"
    receipt = f"booking_{booking.id}"

    client = get_razorpay_client()
    try:
        order = client.order.create(
            {
                "amount": amount_paise,
                "currency": currency,
                "receipt": receipt,
            }
        )
    except Exception as exc:
        logger.exception("Failed to create Razorpay order: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create Razorpay order",
        ) from exc

    payment = Payment(
        booking_id=booking.id,
        provider="razorpay",
        provider_order_id=order["id"],
        amount_paise=amount_paise,
        currency=currency,
        status=PaymentStatus.CREATED,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    return CreateOrderResponse(
        order_id=order["id"],
        amount=amount_paise,
        currency=currency,
        key_id=settings.razorpay_key_id,
    )


@router.post("/verify", response_model=VerifyPaymentResponse)
def verify_payment(
    payload: VerifyPaymentRequest,
    db: Annotated[Session, Depends(get_db)],
):
    payment = db.scalar(
        select(Payment).where(Payment.provider_order_id == payload.razorpay_order_id)
    )

    client = get_razorpay_client()
    try:
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": payload.razorpay_order_id,
                "razorpay_payment_id": payload.razorpay_payment_id,
                "razorpay_signature": payload.razorpay_signature,
            }
        )
    except Exception as exc:
        if payment is not None and payment.status != PaymentStatus.PAID:
            payment.status = PaymentStatus.FAILED
            payment.provider_payment_id = payload.razorpay_payment_id
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment verification failed: invalid signature",
        ) from exc

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment record not found for this order",
        )

    confirm_payment_and_booking(db, payment, payload.razorpay_payment_id)

    return VerifyPaymentResponse(
        status="success",
        message="Payment verified and booking confirmed",
        booking_id=payment.booking_id,
    )


@router.post("/webhook")
async def handle_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_razorpay_signature: Annotated[str | None, Header()] = None,
):
    raw_body = await request.body()
    if not x_razorpay_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Razorpay-Signature header",
        )

    client = get_razorpay_client()
    try:
        client.utility.verify_webhook_signature(
            raw_body.decode("utf-8"),
            x_razorpay_signature,
            settings.razorpay_webhook_secret,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        ) from exc

    try:
        event_data = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc

    event_type = event_data.get("event")
    payment_entity = (
        event_data.get("payload", {}).get("payment", {}).get("entity", {})
    )
    order_id = payment_entity.get("order_id")
    payment_id = payment_entity.get("id")

    if order_id:
        payment = db.scalar(
            select(Payment).where(Payment.provider_order_id == order_id)
        )
        if payment is not None:
            if event_type in ("payment.captured", "order.paid"):
                confirm_payment_and_booking(db, payment, payment_id or "")
            elif event_type == "payment.failed":
                if payment.status != PaymentStatus.PAID:
                    payment.status = PaymentStatus.FAILED
                    payment.provider_payment_id = payment_id
                    db.commit()

    return {"status": "ok"}


@router.post("/pay-at-appointment", response_model=PayAtAppointmentResponse)
def pay_at_appointment(
    payload: PayAtAppointmentRequest,
    db: Annotated[Session, Depends(get_db)],
):
    booking = db.get(Appointment, payload.booking_id)
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    if booking.status == AppointmentStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Booking is cancelled and cannot be confirmed",
        )

    if booking.status != AppointmentStatus.CONFIRMED:
        booking.status = AppointmentStatus.CONFIRMED
        booking.confirmed_at = datetime.now(UTC)
        db.commit()
        try:
            enqueue_confirmation_notification(booking)
        except Exception as exc:
            logger.warning(
                "Unable to enqueue confirmation notification for %s: %s",
                booking.id,
                exc,
            )
        try:
            schedule_appointment_notifications(booking)
        except Exception as exc:
            logger.warning(
                "Unable to schedule appointment notifications for %s: %s",
                booking.id,
                exc,
            )
    else:
        db.commit()

    return PayAtAppointmentResponse(
        status="success",
        message="Appointment confirmed to be paid at appointment",
        booking_id=booking.id,
    )
