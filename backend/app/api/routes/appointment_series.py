import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import require_role
from app.db.database import get_db
from app.models.user import User, UserRole
from app.schemas.appointment_series import (
    AppointmentSeriesCancellationResponse,
    AppointmentSeriesCreate,
    AppointmentSeriesOccurrenceResponse,
    AppointmentSeriesResponse,
)
from app.services.appointment_series import (
    AppointmentSeriesCancellationConflictError,
    AppointmentSeriesNotFoundError,
    AppointmentSeriesPersistenceError,
    RecurringBookingConflictError,
    cancel_appointment_series,
    create_appointment_series,
)
from app.services.booking import BookingValidationError
from app.services.recurrence import RecurrenceValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/appointment-series", tags=["Appointment Series"])


@router.post(
    "", response_model=AppointmentSeriesResponse, status_code=status.HTTP_201_CREATED
)
def create_appointment_series_endpoint(
    payload: AppointmentSeriesCreate,
    db: Annotated[Session, Depends(get_db)],
    customer: Annotated[User, Depends(require_role(UserRole.CUSTOMER))],
):
    try:
        series, appointments = create_appointment_series(db, payload, customer)
    except RecurringBookingConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(error),
                "conflicts": [conflict.__dict__ for conflict in error.conflicts],
            },
        ) from error
    except RecurrenceValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    except BookingValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except AppointmentSeriesPersistenceError as error:
        logger.exception("Unable to persist appointment series")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create appointment series",
        ) from error

    return AppointmentSeriesResponse(
        id=series.id,
        service_id=series.service_id,
        provider_id=series.provider_id,
        frequency=series.frequency,
        interval=series.interval,
        start_date=series.start_date,
        local_start_time=series.local_start_time,
        timezone=series.timezone,
        end_mode=series.end_mode,
        occurrence_count=series.occurrence_count,
        end_date=series.end_date,
        status=series.status,
        occurrences=[
            AppointmentSeriesOccurrenceResponse.model_validate(appointment)
            for appointment in appointments
        ],
    )


@router.delete("/{series_id}", response_model=AppointmentSeriesCancellationResponse)
def cancel_appointment_series_endpoint(
    series_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    customer: Annotated[User, Depends(require_role(UserRole.CUSTOMER))],
):
    try:
        series, cancelled_ids = cancel_appointment_series(db, series_id, customer)
    except AppointmentSeriesNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment series not found",
        ) from error
    except AppointmentSeriesCancellationConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Appointment series is already cancelled",
        ) from error
    except AppointmentSeriesPersistenceError as error:
        logger.exception("Unable to cancel appointment series")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to cancel appointment series",
        ) from error

    return AppointmentSeriesCancellationResponse(
        series_id=series.id,
        status=series.status,
        appointments_cancelled=len(cancelled_ids),
        cancelled_appointment_ids=cancelled_ids,
    )
