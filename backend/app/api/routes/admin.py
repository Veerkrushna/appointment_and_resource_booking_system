from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.timezones import TimezoneValidationError, get_timezone, to_utc
from app.db.database import get_db
from app.models.appointment import Appointment, AppointmentStatus
from app.models.providers import AvailabilityStatus, Provider
from app.models.service import Service, ServiceStatus
from app.schemas.admin import (
    AdminAppointmentListResponse,
    AdminAppointmentResponse,
    AdminOverviewResponse,
    AppointmentStatusCount,
    ProviderScheduleResponse,
)
from app.schemas.providers import AvailabilityWindow, BlackoutResponse, BreakWindow

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def _admin_timezone(timezone: str):
    try:
        return get_timezone(timezone)
    except TimezoneValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def _utc_day_bounds(target_date: date, timezone: str) -> tuple[datetime, datetime]:
    """Build UTC bounds from an admin's local date, including DST transitions."""
    start = to_utc(datetime.combine(target_date, time.min), timezone)
    end = to_utc(datetime.combine(target_date + timedelta(days=1), time.min), timezone)
    return start, end


def _appointment_response(appointment: Appointment, timezone: str):
    return AdminAppointmentResponse.from_records(
        appointment,
        appointment.provider.name,
        appointment.service.name,
        timezone,
    )


@router.get("/overview", response_model=AdminOverviewResponse)
def admin_overview(
    db: Annotated[Session, Depends(get_db)],
    timezone: str = Query(default="UTC", min_length=1, max_length=64),
):
    _admin_timezone(timezone)
    now_utc = datetime.now(UTC)
    local_today = now_utc.astimezone(get_timezone(timezone)).date()
    today_start, today_end = _utc_day_bounds(local_today, timezone)

    status_rows = db.execute(
        select(Appointment.status, func.count(Appointment.id))
        .group_by(Appointment.status)
        .order_by(Appointment.status)
    ).all()
    total_appointments = sum(count for _, count in status_rows)
    upcoming_appointments = (
        db.scalar(
            select(func.count(Appointment.id)).where(
                Appointment.appointment_end >= now_utc,
                Appointment.status != AppointmentStatus.CANCELLED,
            )
        )
        or 0
    )
    appointments_today = (
        db.scalar(
            select(func.count(Appointment.id)).where(
                Appointment.appointment_start < today_end,
                Appointment.appointment_end > today_start,
            )
        )
        or 0
    )

    return AdminOverviewResponse(
        generated_at=now_utc,
        timezone=timezone,
        total_appointments=total_appointments,
        upcoming_appointments=upcoming_appointments,
        appointments_today=appointments_today,
        appointments_by_status=[
            AppointmentStatusCount(status=appointment_status.value, count=count)
            for appointment_status, count in status_rows
        ],
        total_providers=db.scalar(select(func.count(Provider.id))) or 0,
        active_providers=db.scalar(
            select(func.count(Provider.id)).where(
                Provider.availability_status == AvailabilityStatus.AVAILABLE
            )
        )
        or 0,
        total_services=db.scalar(select(func.count(Service.id))) or 0,
        active_services=db.scalar(
            select(func.count(Service.id)).where(Service.status == ServiceStatus.ACTIVE)
        )
        or 0,
    )


@router.get("/appointments", response_model=AdminAppointmentListResponse)
def admin_appointments(
    db: Annotated[Session, Depends(get_db)],
    timezone: str = Query(default="UTC", min_length=1, max_length=64),
    provider_id: UUID | None = None,
    service_id: UUID | None = None,
    appointment_status: Annotated[
        AppointmentStatus | None, Query(alias="status")
    ] = None,
    search: str | None = None,
    provider_search: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = Query(default=1, ge=1),
):
    _admin_timezone(timezone)

    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=400, detail="start_date must be before or equal to end_date"
        )

    page_size = 15

    query = (
        select(Appointment)
        .join(Provider, Provider.id == Appointment.provider_id)
        .options(
            joinedload(Appointment.provider),
            joinedload(Appointment.service),
        )
    )
    count_query = select(func.count(Appointment.id)).join(
        Provider, Provider.id == Appointment.provider_id
    )
    filters = []
    if provider_id is not None:
        filters.append(Appointment.provider_id == provider_id)
    if service_id is not None:
        filters.append(Appointment.service_id == service_id)
    if appointment_status is not None:
        filters.append(Appointment.status == appointment_status)
    if search is not None:
        search_term = f"%{search.strip()}%"
        filters.append(
            or_(
                Appointment.user_email.ilike(search_term),
                Appointment.user_phone.ilike(search_term),
            )
        )
    if provider_search is not None:
        provider_search_term = f"%{provider_search.strip()}%"
        filters.append(Provider.name.ilike(provider_search_term))
    if start_date is not None:
        filters.append(
            Appointment.appointment_end > _utc_day_bounds(start_date, timezone)[0]
        )
    if end_date is not None:
        filters.append(
            Appointment.appointment_start < _utc_day_bounds(end_date, timezone)[1]
        )
    query = query.where(*filters).order_by(Appointment.appointment_start)
    count_query = count_query.where(*filters)

    total = db.scalar(count_query) or 0
    appointments = db.scalars(
        query.offset((page - 1) * page_size).limit(page_size)
    ).all()
    return AdminAppointmentListResponse(
        appointments=[_appointment_response(item, timezone) for item in appointments],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get(
    "/providers/{provider_id}/schedule", response_model=ProviderScheduleResponse
)
def admin_provider_schedule(
    provider_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    timezone: str = Query(default="UTC", min_length=1, max_length=64),
    start_date: date | None = None,
    end_date: date | None = None,
):
    _admin_timezone(timezone)
    provider = db.scalar(
        select(Provider)
        .options(
            selectinload(Provider.availability),
            selectinload(Provider.breaks),
            selectinload(Provider.blackout_dates),
        )
        .where(Provider.id == provider_id)
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    local_today = datetime.now(UTC).astimezone(get_timezone(timezone)).date()
    schedule_start = start_date or local_today
    schedule_end = end_date or schedule_start + timedelta(days=6)
    if schedule_start > schedule_end:
        raise HTTPException(
            status_code=400, detail="start_date must be before end_date"
        )

    range_start, _ = _utc_day_bounds(schedule_start, timezone)
    _, range_end = _utc_day_bounds(schedule_end, timezone)
    appointments = db.scalars(
        select(Appointment)
        .options(joinedload(Appointment.provider), joinedload(Appointment.service))
        .where(
            Appointment.provider_id == provider_id,
            Appointment.appointment_start < range_end,
            Appointment.appointment_end > range_start,
        )
        .order_by(Appointment.appointment_start)
    ).all()

    return ProviderScheduleResponse(
        provider=provider,
        timezone=timezone,
        start_date=schedule_start,
        end_date=schedule_end,
        availability=[
            AvailabilityWindow(
                day_of_week=item.day_of_week,
                start_time=item.start_time,
                end_time=item.end_time,
                is_working_day=item.is_working_day,
            )
            for item in sorted(provider.availability, key=lambda item: item.day_of_week)
        ],
        breaks=[
            BreakWindow(
                day_of_week=item.day_of_week,
                start_time=item.start_time,
                end_time=item.end_time,
                break_type=item.break_type,
            )
            for item in sorted(
                provider.breaks, key=lambda item: (item.day_of_week, item.start_time)
            )
        ],
        blackout_dates=[
            BlackoutResponse.model_validate(item) for item in provider.blackout_dates
        ],
        appointments=[_appointment_response(item, timezone) for item in appointments],
    )
