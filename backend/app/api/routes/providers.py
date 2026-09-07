# FastAPI dependencies are intentionally declared in function signatures.
# ruff: noqa: B008
from datetime import date, datetime, time, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.crud.provider_services import (
    get_provider_services,
    update_provider_services,
)
from app.crud.providers import create_provider as create_provider_record
from app.crud.providers import get_provider, replace_provider_availability
from app.crud.providers import list_providers as list_provider_records
from app.crud.providers import update_provider as update_provider_record
from app.db.database import get_db
from app.models.providers import Provider
from app.schemas.provider_service import (
    ProviderServiceResponse,
    ProviderServicesUpdate,
)
from app.schemas.providers import (
    AvailabilityRequest,
    AvailabilityWindow,
    BlackoutWindow,
    BreakWindow,
    ProviderCreate,
    ProviderResponse,
    ProviderUpdate,
    ScheduleResponse,
)

router = APIRouter(prefix="/api/providers", tags=["Providers"])


def get_provider_or_404(provider_id: UUID, db: Session) -> Provider:
    provider = get_provider(db, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


def availability_response(provider: Provider) -> list[AvailabilityWindow]:
    return [
        AvailabilityWindow(
            day_of_week=item.day_of_week,
            start_time=item.start_time,
            end_time=item.end_time,
            is_working_day=item.is_working_day,
        )
        for item in sorted(provider.availability, key=lambda item: item.day_of_week)
    ]


def break_response(provider: Provider) -> list[BreakWindow]:
    return [
        BreakWindow(
            day_of_week=item.day_of_week,
            start_time=item.start_time,
            end_time=item.end_time,
            break_type=item.break_type,
        )
        for item in sorted(
            provider.breaks, key=lambda item: (item.day_of_week, item.start_time)
        )
    ]


def blackout_response(provider: Provider) -> list[BlackoutWindow]:
    return [
        BlackoutWindow(
            blackout_start=item.blackout_start,
            blackout_end=item.blackout_end,
            reason=item.reason,
            is_all_day=item.is_all_day,
        )
        for item in sorted(
            provider.blackout_dates, key=lambda item: item.blackout_start
        )
    ]


@router.post("", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
def create_provider(payload: ProviderCreate, db: Session = Depends(get_db)):
    return create_provider_record(db, payload)


@router.get("", response_model=list[ProviderResponse])
def list_providers(
    db: Session = Depends(get_db),
    provider_type: str | None = Query(default=None, alias="type"),
    availability_status: str | None = None,
):
    return list_provider_records(db, provider_type, availability_status)


@router.get(
    "/{provider_id}/services",
    response_model=list[ProviderServiceResponse],
)
def get_services_for_provider(
    provider_id: UUID,
    db: Session = Depends(get_db),
):
    provider = get_provider(
        db=db,
        provider_id=provider_id,
    )

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )

    return get_provider_services(
        db=db,
        provider_id=provider_id,
    )


@router.put(
    "/{provider_id}/services",
    response_model=list[ProviderServiceResponse],
)
def update_services_for_provider(
    provider_id: UUID,
    payload: ProviderServicesUpdate,
    db: Session = Depends(get_db),
):
    provider = get_provider(
        db=db,
        provider_id=provider_id,
    )

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )

    try:
        return update_provider_services(
            db=db,
            provider_id=provider_id,
            service_ids=payload.service_ids,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error


@router.put("/{provider_id}", response_model=ProviderResponse)
def update_provider(
    provider_id: UUID,
    payload: ProviderUpdate,
    db: Session = Depends(get_db),
):
    provider = get_provider_or_404(provider_id, db)
    return update_provider_record(db, provider, payload)


@router.post("/{provider_id}/availability", response_model=ScheduleResponse)
def set_provider_availability(
    provider_id: UUID,
    payload: AvailabilityRequest,
    db: Session = Depends(get_db),
):
    provider = get_provider_or_404(provider_id, db)
    provider = replace_provider_availability(db, provider, payload)
    return build_schedule(provider, None)


@router.get("/{provider_id}/schedule", response_model=ScheduleResponse)
def get_provider_schedule(
    provider_id: UUID,
    schedule_date: date | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
):
    provider = get_provider_or_404(provider_id, db)
    return build_schedule(provider, schedule_date)


def build_schedule(provider: Provider, schedule_date: date | None) -> ScheduleResponse:
    availability = availability_response(provider)
    breaks = break_response(provider)
    blackouts = blackout_response(provider)

    if schedule_date is not None:
        day_of_week = schedule_date.weekday()
        availability = [
            item for item in availability if item.day_of_week == day_of_week
        ]
        breaks = [item for item in breaks if item.day_of_week == day_of_week]
        blackouts = [
            item
            for item in blackouts
            if item.blackout_start
            < datetime.combine(
                schedule_date, time.min, tzinfo=item.blackout_start.tzinfo
            )
            + timedelta(days=1)
            and item.blackout_end
            > datetime.combine(
                schedule_date, time.min, tzinfo=item.blackout_start.tzinfo
            )
        ]

    return ScheduleResponse(
        provider=provider,
        date=schedule_date,
        availability=availability,
        breaks=breaks,
        blackout_dates=blackouts,
    )
