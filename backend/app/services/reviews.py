from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.models.appointment import Appointment, AppointmentStatus
from app.models.providers import ProviderType
from app.models.review import Review
from app.models.user import User
from app.schemas.review import ReviewCreate, ReviewUpdate


class ReviewServiceError(Exception):
    pass


class AppointmentNotFoundError(ReviewServiceError):
    pass


class ReviewNotFoundError(ReviewServiceError):
    pass


class ReviewPermissionError(ReviewServiceError):
    pass


class AppointmentNotCompletedError(ReviewServiceError):
    pass


class ProviderNotReviewableError(ReviewServiceError):
    pass


class ReviewAlreadyExistsError(ReviewServiceError):
    pass


class ReviewPersistenceError(ReviewServiceError):
    pass


def _raise_persistence_error(db: Session, error: SQLAlchemyError) -> None:
    db.rollback()
    raise ReviewPersistenceError from error


def _ensure_reviewable_provider(appointment: Appointment) -> None:
    if appointment.provider.type != ProviderType.PERSON:
        raise ProviderNotReviewableError


def create_review(db: Session, customer: User, payload: ReviewCreate) -> Review:
    try:
        appointment = db.get(Appointment, payload.appointment_id)
        if appointment is None:
            raise AppointmentNotFoundError
        if appointment.customer_id != customer.id:
            raise ReviewPermissionError
        if appointment.status != AppointmentStatus.COMPLETED:
            raise AppointmentNotCompletedError
        _ensure_reviewable_provider(appointment)
        if (
            db.scalar(select(Review.id).where(Review.appointment_id == appointment.id))
            is not None
        ):
            raise ReviewAlreadyExistsError

        review = Review(
            appointment_id=appointment.id,
            customer_id=customer.id,
            provider_id=appointment.provider_id,
            rating=payload.rating,
            comment=payload.comment,
        )
        db.add(review)
        try:
            db.commit()
        except IntegrityError as error:
            db.rollback()
            constraint_name = getattr(
                getattr(error.orig, "diag", None), "constraint_name", None
            )
            if constraint_name == "uq_reviews_appointment_id":
                raise ReviewAlreadyExistsError from error
            raise ReviewPersistenceError from error
        db.refresh(review)
        return review
    except ReviewServiceError:
        raise
    except SQLAlchemyError as error:
        _raise_persistence_error(db, error)


def get_review_for_appointment(
    db: Session, appointment_id: UUID, customer: User
) -> Review:
    try:
        appointment = db.get(Appointment, appointment_id)
        if appointment is None:
            raise AppointmentNotFoundError
        if appointment.customer_id != customer.id:
            raise ReviewPermissionError
        _ensure_reviewable_provider(appointment)

        review = db.scalar(
            select(Review).where(Review.appointment_id == appointment.id)
        )
        if review is None:
            raise ReviewNotFoundError
        return review
    except ReviewServiceError:
        raise
    except SQLAlchemyError as error:
        _raise_persistence_error(db, error)


def update_review(
    db: Session, review_id: UUID, customer: User, payload: ReviewUpdate
) -> Review:
    try:
        review = db.scalar(
            select(Review)
            .where(Review.id == review_id)
            .options(joinedload(Review.appointment))
        )
        if review is None:
            raise ReviewNotFoundError
        if (
            review.customer_id != customer.id
            or review.appointment.customer_id != customer.id
        ):
            raise ReviewPermissionError
        _ensure_reviewable_provider(review.appointment)

        review.rating = payload.rating
        review.comment = payload.comment
        db.commit()
        db.refresh(review)
        return review
    except ReviewServiceError:
        raise
    except SQLAlchemyError as error:
        _raise_persistence_error(db, error)
