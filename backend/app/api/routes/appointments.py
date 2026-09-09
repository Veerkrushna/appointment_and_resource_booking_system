from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.appointment import Appointment, AppointmentStatus
from app.schemas.appointment import (
    AppointmentCancellationCreate,
    AppointmentCancellationResponse,
    AppointmentCreate,
    AppointmentResponse,
    AppointmentUpdate,
)
from app.services.booking import (
    BookingConflictError,
    BookingValidationError,
    cancel_appointment,
    create_appointment,
    update_appointment,
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


@router.get("", response_model=list[AppointmentResponse])
def list_appointments(
    db: Annotated[Session, Depends(get_db)],
    provider_id: UUID | None = None,
    user_email: str | None = None,
    appointment_status: Annotated[
        AppointmentStatus | None, Query(alias="status")
    ] = None,
):
    query = select(Appointment).order_by(Appointment.appointment_start)
    if provider_id is not None:
        query = query.where(Appointment.provider_id == provider_id)
    if user_email is not None:
        query = query.where(Appointment.user_email == user_email)
    if appointment_status is not None:
        query = query.where(Appointment.status == appointment_status)
    return list(db.scalars(query).all())


@router.get("/{appointment_id}", response_model=AppointmentResponse)
def get_appointment(
    appointment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
):
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )
    return appointment


@router.put("/{appointment_id}", response_model=AppointmentResponse)
def edit_appointment(
    appointment_id: UUID,
    payload: AppointmentUpdate,
    db: Annotated[Session, Depends(get_db)],
):
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )
    try:
        return update_appointment(db, appointment, payload)
    except BookingConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except BookingValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error


@router.post(
    "/{appointment_id}/cancel",
    response_model=AppointmentCancellationResponse,
    status_code=status.HTTP_201_CREATED,
)
def cancel_appointment_endpoint(
    appointment_id: UUID,
    payload: AppointmentCancellationCreate,
    db: Annotated[Session, Depends(get_db)],
):
    try:
        return cancel_appointment(db, appointment_id, payload)
    except BookingValidationError as error:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if str(error) == "Appointment not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.get(
    "/{appointment_id}/cancellations",
    response_model=list[AppointmentCancellationResponse],
)
def list_appointment_cancellations(
    appointment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
):
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )
    return appointment.cancellations
