from datetime import UTC, date, datetime, time, timedelta
from typing import Sequence
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment, AppointmentStatus
from app.models.providers import Provider


def get_appointments_list(
    db: Session,
    timezone: str,
    page: int = 1,
    page_size: int = 15,
    provider_id: UUID | None = None,
    user_email: str | None = None,
    appointment_status: AppointmentStatus | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    search: str | None = None,
    provider_search: str | None = None,
) -> tuple[Sequence[Appointment], int, int]:
    query = (
        select(Appointment)
        .join(Provider, Provider.id == Appointment.provider_id)
        .order_by(Appointment.appointment_start)
    )

    if start_date is not None:
        start_datetime = datetime.combine(
            start_date,
            time.min,
            tzinfo=ZoneInfo(timezone),
        ).astimezone(UTC)
        query = query.where(Appointment.appointment_start >= start_datetime)

    if end_date is not None:
        end_datetime = datetime.combine(
            end_date + timedelta(days=1),
            time.min,
            tzinfo=ZoneInfo(timezone),
        ).astimezone(UTC)

        query = query.where(Appointment.appointment_start < end_datetime)

    if provider_id is not None:
        query = query.where(Appointment.provider_id == provider_id)
    if provider_search is not None:
        provider_search_term = f"%{provider_search.strip()}%"
        query = query.where(Provider.name.ilike(provider_search_term))
    if user_email is not None:
        query = query.where(Appointment.user_email == user_email)
    if appointment_status is not None:
        query = query.where(Appointment.status == appointment_status)
    if search is not None:
        search_term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Appointment.user_email.ilike(search_term),
                Appointment.user_phone.ilike(search_term),
            )
        )

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    start_index = (page - 1) * page_size
    appointments = db.scalars(query.offset(start_index).limit(page_size)).all()
    total_pages = (total + page_size - 1) // page_size if total else 0

    return appointments, total or 0, total_pages
