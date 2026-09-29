from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import require_role
from app.db.database import get_db
from app.models.user import User, UserRole
from app.schemas.review import ReviewCreate, ReviewResponse, ReviewUpdate
from app.services.reviews import (
    AppointmentNotCompletedError,
    AppointmentNotFoundError,
    ProviderNotReviewableError,
    ReviewAlreadyExistsError,
    ReviewNotFoundError,
    ReviewPermissionError,
    ReviewPersistenceError,
    create_review,
    get_review_for_appointment,
    update_review,
)

router = APIRouter(prefix="/api/reviews", tags=["Reviews"])


def _raise_review_error(error: Exception) -> None:
    if isinstance(error, AppointmentNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
        detail = "Appointment not found"
    elif isinstance(error, ReviewNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
        detail = "Review not found"
    elif isinstance(error, ReviewPermissionError):
        status_code = status.HTTP_403_FORBIDDEN
        detail = "You are not allowed to access this review"
    elif isinstance(error, AppointmentNotCompletedError):
        status_code = status.HTTP_400_BAD_REQUEST
        detail = "Only completed appointments can be reviewed"
    elif isinstance(error, ProviderNotReviewableError):
        status_code = status.HTTP_400_BAD_REQUEST
        detail = "Only person providers can be reviewed"
    elif isinstance(error, ReviewAlreadyExistsError):
        status_code = status.HTTP_409_CONFLICT
        detail = "This appointment has already been reviewed"
    elif isinstance(error, ReviewPersistenceError):
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = "Unable to process review"
    else:
        raise error
    raise HTTPException(status_code=status_code, detail=detail) from error


@router.post("", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
def create_review_endpoint(
    payload: ReviewCreate,
    db: Annotated[Session, Depends(get_db)],
    customer: Annotated[User, Depends(require_role(UserRole.CUSTOMER))],
):
    try:
        return create_review(db, customer, payload)
    except (
        AppointmentNotCompletedError,
        AppointmentNotFoundError,
        ReviewAlreadyExistsError,
        ReviewPermissionError,
        ReviewPersistenceError,
        ProviderNotReviewableError,
    ) as error:
        _raise_review_error(error)


@router.get("/appointment/{appointment_id}", response_model=ReviewResponse)
def get_appointment_review_endpoint(
    appointment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    customer: Annotated[User, Depends(require_role(UserRole.CUSTOMER))],
):
    try:
        return get_review_for_appointment(db, appointment_id, customer)
    except (
        AppointmentNotFoundError,
        ProviderNotReviewableError,
        ReviewNotFoundError,
        ReviewPermissionError,
    ) as error:
        _raise_review_error(error)
    except ReviewPersistenceError as error:
        _raise_review_error(error)


@router.put("/{review_id}", response_model=ReviewResponse)
def update_review_endpoint(
    review_id: UUID,
    payload: ReviewUpdate,
    db: Annotated[Session, Depends(get_db)],
    customer: Annotated[User, Depends(require_role(UserRole.CUSTOMER))],
):
    try:
        return update_review(db, review_id, customer, payload)
    except (
        ProviderNotReviewableError,
        ReviewNotFoundError,
        ReviewPermissionError,
        ReviewPersistenceError,
    ) as error:
        _raise_review_error(error)
