from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_customer, require_role
from app.core.timezones import get_timezone
from app.db.database import get_db
from app.models.appointment import Appointment
from app.models.customer import Customer
from app.models.user import UserRole
from app.schemas.appointment import (
    AppointmentCancellationCreate,
    AppointmentListResponse,
    AppointmentRescheduleCreate,
    AppointmentResponse,
)
from app.services.booking import (
    BookingConflictError,
    BookingValidationError,
    cancel_appointment,
    reschedule_appointment,
)

router = APIRouter(prefix="/api/customer/appointments", tags=["Customer Appointments"], dependencies=[Depends(require_role(UserRole.CUSTOMER, UserRole.PROVIDER))])


def _owned(db: Session, appointment_id: UUID, customer: Customer) -> Appointment:
    appointment = db.scalar(select(Appointment).where(Appointment.id == appointment_id, Appointment.customer_id == customer.id).options(joinedload(Appointment.service), joinedload(Appointment.provider)))
    if appointment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return appointment


@router.get("", response_model=AppointmentListResponse)
def list_customer_appointments(customer: Annotated[Customer, Depends(get_current_customer)], db: Annotated[Session, Depends(get_db)], timezone: str = Query(default="UTC"), page: int = Query(default=1, ge=1)):
    get_timezone(timezone)
    page_size = 15
    query = select(Appointment).where(Appointment.customer_id == customer.id).order_by(Appointment.appointment_start)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    appointments = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return AppointmentListResponse(appointments=[AppointmentResponse.from_appointment(item, timezone) for item in appointments], page=page, page_size=page_size, total=total, total_pages=(total + page_size - 1) // page_size)


@router.get("/{appointment_id}", response_model=AppointmentResponse)
def get_customer_appointment(appointment_id: UUID, customer: Annotated[Customer, Depends(get_current_customer)], db: Annotated[Session, Depends(get_db)], timezone: str = Query(default="UTC")):
    get_timezone(timezone)
    return AppointmentResponse.from_appointment(_owned(db, appointment_id, customer), timezone)


@router.post("/{appointment_id}/cancel", status_code=status.HTTP_201_CREATED)
def cancel_customer_appointment(appointment_id: UUID, payload: AppointmentCancellationCreate, customer: Annotated[Customer, Depends(get_current_customer)], db: Annotated[Session, Depends(get_db)]):
    _owned(db, appointment_id, customer)
    try:
        return cancel_appointment(db, appointment_id, payload)
    except BookingValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post("/{appointment_id}/reschedule", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
def reschedule_customer_appointment(appointment_id: UUID, payload: AppointmentRescheduleCreate, customer: Annotated[Customer, Depends(get_current_customer)], db: Annotated[Session, Depends(get_db)], timezone: str = Query(default="UTC")):
    get_timezone(timezone)
    _owned(db, appointment_id, customer)
    try:
        return AppointmentResponse.from_appointment(reschedule_appointment(db, appointment_id, payload), timezone)
    except BookingConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except BookingValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
