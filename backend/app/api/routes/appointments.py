from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.security import get_optional_customer
from app.core.timezones import TimezoneValidationError, get_timezone
from app.crud.appointments import get_appointments_list
from app.db.database import get_db
from app.models.appointment import Appointment, AppointmentStatus
from app.models.customer import Customer
from app.models.providers import Provider
from app.schemas.appointment import (
    AppointmentCancellationCreate,
    AppointmentCancellationResponse,
    AppointmentCreate,
    AppointmentListResponse,
    AppointmentRescheduleCreate,
    AppointmentResponse,
    AppointmentUpdate,
)
from app.services.booking import (
    BookingConflictError,
    BookingValidationError,
    CancellationValidationError,
    cancel_appointment,
    create_appointment,
    reschedule_appointment,
    update_appointment,
)

router = APIRouter(prefix="/api/appointments", tags=["Appointments"])


def _validate_timezone(timezone: str) -> str:
    try:
        get_timezone(timezone)
    except TimezoneValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error
    return timezone


@router.post(
    "", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED
)
def book_appointment(
    payload: AppointmentCreate,
    db: Annotated[Session, Depends(get_db)],
    customer: Annotated[Customer | None, Depends(get_optional_customer)],
    timezone: str = Query(default="UTC", min_length=1, max_length=64),
):
    timezone = _validate_timezone(timezone)
    try:
        appointment = create_appointment(db, payload, customer)
        return AppointmentResponse.from_appointment(appointment, timezone)
    except BookingConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except BookingValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error


@router.get("", response_model=AppointmentListResponse)
def list_appointments(
    db: Annotated[Session, Depends(get_db)],
    provider_id: UUID | None = None,
    user_email: str | None = None,
    timezone: str = Query(default="UTC", min_length=1, max_length=64),
    appointment_status: Annotated[
        AppointmentStatus | None, Query(alias="status")
    ] = None,
    page: Annotated[
        int,
        Query(ge=1, description="Page number"),
    ] = 1,
    start_date: date | None = None,
    end_date: date | None = None,
    search: str | None = None,
    provider_search: str | None = None,
    page_size: int = Query(default=15, ge=1, le=100, description="Page size"),
):
    timezone = _validate_timezone(timezone)

    if start_date is not None and end_date is not None:
        if start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date must be before or equal to end_date",
            )


    appointments, total, total_pages = get_appointments_list(
        db=db,
        timezone=timezone,
        page=page,
        page_size=page_size,
        provider_id=provider_id,
        user_email=user_email,
        appointment_status=appointment_status,
        start_date=start_date,
        end_date=end_date,
        search=search,
        provider_search=provider_search,
    )

    return AppointmentListResponse(
        appointments=[
            AppointmentResponse.from_appointment(appointment, timezone)
            for appointment in appointments
        ],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.get("/{appointment_id}", response_model=AppointmentResponse)
def get_appointment(
    appointment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    timezone: str = Query(default="UTC", min_length=1, max_length=64),
):
    timezone = _validate_timezone(timezone)
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )
    return AppointmentResponse.from_appointment(appointment, timezone)


@router.put("/{appointment_id}", response_model=AppointmentResponse)
def edit_appointment(
    appointment_id: UUID,
    payload: AppointmentUpdate,
    db: Annotated[Session, Depends(get_db)],
    timezone: str = Query(default="UTC", min_length=1, max_length=64),
):
    timezone = _validate_timezone(timezone)
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )
    try:
        appointment = update_appointment(db, appointment, payload)
        return AppointmentResponse.from_appointment(appointment, timezone)
    except BookingConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except BookingValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_appointment_endpoint(
    appointment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    payload: AppointmentCancellationCreate | None = None,
):
    try:
        cancel_appointment(db, appointment_id, payload)
    except CancellationValidationError as error:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if str(error) == "Appointment not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.post(
    "/{appointment_id}/cancel",
    response_model=AppointmentCancellationResponse,
    status_code=status.HTTP_201_CREATED,
)
def cancel_appointment_post_endpoint(
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


@router.post(
    "/{appointment_id}/reschedule",
    response_model=AppointmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def reschedule_appointment_endpoint(
    appointment_id: UUID,
    payload: AppointmentRescheduleCreate,
    db: Annotated[Session, Depends(get_db)],
):
    try:
        return reschedule_appointment(db, appointment_id, payload)
    except BookingConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
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
