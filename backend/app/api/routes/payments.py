from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import require_role
from app.db.database import get_db
from app.models.user import User, UserRole
from app.schemas.payment import AppointmentPaymentOrderCreate, PaymentOrderResponse
from app.services.booking import BookingConflictError, BookingValidationError
from app.services.payment_orders import create_appointment_payment_order
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
