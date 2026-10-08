from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import require_role
from app.db.database import get_db
from app.models.user import User, UserRole
from app.schemas.payment import (
    AppointmentPaymentOrderCreate,
    PaymentOrderResponse,
    PaymentVerificationRequest,
    PaymentVerificationResponse,
)
from app.services.booking import BookingConflictError, BookingValidationError
from app.services.payment_orders import create_appointment_payment_order
from app.services.payment_verification import (
    InvalidPaymentVerificationError,
    PaymentNotFoundError,
    PaymentStateConflictError,
    verify_appointment_payment,
)
from app.services.razorpay import RazorpayIntegrationError

router = APIRouter(prefix="/api/payments", tags=["Payments"])


@router.post(
    "/order",
    response_model=PaymentOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_payment_order_endpoint(
    payload: AppointmentPaymentOrderCreate,
    db: Annotated[Session, Depends(get_db)],
    customer: Annotated[User, Depends(require_role(UserRole.CUSTOMER))],
) -> PaymentOrderResponse:
    try:
        payment = create_appointment_payment_order(db, customer, payload)
    except BookingConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except BookingValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error
    except RazorpayIntegrationError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to create payment order",
        ) from error

    return PaymentOrderResponse(
        payment_id=payment.id,
        key_id=settings.razorpay_key_id or "",
        order_id=payment.provider_order_id,
        amount=payment.amount,
        currency=payment.currency,
        hold_expires_at=payment.booking_holds[0].expires_at,
    )


@router.post("/verify", response_model=PaymentVerificationResponse)
def verify_payment_endpoint(
    payload: PaymentVerificationRequest,
    db: Annotated[Session, Depends(get_db)],
    customer: Annotated[User, Depends(require_role(UserRole.CUSTOMER))],
) -> PaymentVerificationResponse:
    try:
        payment = verify_appointment_payment(db, customer, payload)
    except PaymentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Payment was not found"
        ) from error
    except InvalidPaymentVerificationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment verification failed",
        ) from error
    except (PaymentStateConflictError, BookingConflictError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except BookingValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error
    except RazorpayIntegrationError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to verify payment",
        ) from error

    appointment = payment.appointment
    if (
        appointment is None
        or payment.provider_payment_id is None
        or payment.provider_order_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Verified payment has no appointment",
        )
    return PaymentVerificationResponse(
        payment_id=payment.id,
        provider_payment_id=payment.provider_payment_id,
        order_id=payment.provider_order_id,
        status=payment.status,
        appointment_id=appointment.id,
        appointment_status=appointment.status,
        appointment_start=appointment.appointment_start,
        appointment_end=appointment.appointment_end,
    )
