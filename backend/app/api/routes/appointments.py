from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.appointment import AppointmentCreate, AppointmentResponse
from app.services.booking import (
    BookingConflictError,
    BookingValidationError,
    create_appointment,
)

router = APIRouter(prefix="/api/appointments", tags=["Appointments"])


@router.post(
    "", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED
)
def book_appointment(
    payload: AppointmentCreate,
    db: Annotated[Session, Depends(get_db)],
):
    try:
        return create_appointment(db, payload)
    except BookingConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except BookingValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error
