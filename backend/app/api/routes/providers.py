from datetime import date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.crud.breaks import (
    create_provider_break,
    delete_provider_break,
    get_provider_break,
    get_provider_breaks,
    update_provider_break,
)
from app.crud.provider_services import (
    get_provider_services,
    update_provider_services,
)
from app.crud.providers import create_provider as create_provider_record
from app.crud.providers import (
    create_provider_blackout,
    delete_provider_blackout,
    get_provider,
    list_provider_blackouts,
    replace_provider_availability,
)
from app.crud.providers import list_providers as list_provider_records
from app.crud.providers import update_provider as update_provider_record
from app.db.database import get_db
from app.models.availability import ProviderBlackoutDate
from app.models.providers import Provider
from app.schemas.provider_service import (
    ProviderServiceResponse,
    ProviderServicesUpdate,
)
from app.schemas.providers import (
    AvailabilityRequest,
    AvailabilityWindow,
    BlackoutResponse,
    BreakWindow,
    ProviderBreakCreate,
    ProviderBreakResponse,
    ProviderBreakUpdate,
    ProviderCreate,
    ProviderResponse,
    ProviderUpdate,
    ScheduleResponse,
    UnavailabilityRequest,
)

router = APIRouter(prefix="/api/providers", tags=["Providers"])


def get_provider_or_404(provider_id: UUID, db: Session) -> Provider:
    provider = get_provider(db, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


def breaks_overlap(
    start_time: time,
    end_time: time,
    existing_start: time,
    existing_end: time,
) -> bool:
    return start_time < existing_end and end_time > existing_start


def validate_break_overlap(
    db: Session,
    provider_id: UUID,
    day_of_week: int,
    start_time: time,
    end_time: time,
    exclude_break_id: UUID | None = None,
) -> None:
    existing_breaks = get_provider_breaks(
        db=db,
        provider_id=provider_id,
    )

    for existing_break in existing_breaks:
        if existing_break.day_of_week != day_of_week:
            continue

        if exclude_break_id is not None and existing_break.id == exclude_break_id:
            continue

        if breaks_overlap(
            start_time=start_time,
            end_time=end_time,
            existing_start=existing_break.start_time,
            existing_end=existing_break.end_time,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Break overlaps with an existing break",
            )


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


def blackout_response(provider: Provider) -> list[BlackoutResponse]:
    return [
        BlackoutResponse(
            id=item.id,
            blackout_start=item.blackout_start,
            blackout_end=item.blackout_end,
            reason=item.reason,
            is_all_day=item.is_all_day,
        )
        for item in sorted(
            provider.blackout_dates, key=lambda item: item.blackout_start
        )
    ]


def blackout_item_response(item: ProviderBlackoutDate) -> BlackoutResponse:
    return BlackoutResponse(
        id=item.id,
        blackout_start=item.blackout_start,
        blackout_end=item.blackout_end,
        reason=item.reason,
        is_all_day=item.is_all_day,
    )


@router.post("", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
def create_provider(
    payload: ProviderCreate,
    db: Annotated[Session, Depends(get_db)],
):
    return create_provider_record(db, payload)


@router.get("", response_model=list[ProviderResponse])
def list_providers(
    db: Annotated[Session, Depends(get_db)],
    provider_type: Annotated[str | None, Query(alias="type")] = None,
    availability_status: str | None = None,
):
    return list_provider_records(db, provider_type, availability_status)


@router.get(
    "/{provider_id}/services",
    response_model=list[ProviderServiceResponse],
)
def get_services_for_provider(
    provider_id: UUID,
    db: Annotated[Session, Depends(get_db)],
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
    db: Annotated[Session, Depends(get_db)],
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
    db: Annotated[Session, Depends(get_db)],
):
    provider = get_provider_or_404(provider_id, db)
    return update_provider_record(db, provider, payload)


@router.post(
    "/{provider_id}/breaks",
    response_model=ProviderBreakResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_break_for_provider(
    provider_id: UUID,
    payload: ProviderBreakCreate,
    db: Annotated[Session, Depends(get_db)],
):
    get_provider_or_404(provider_id, db)

    validate_break_overlap(
        db=db,
        provider_id=provider_id,
        day_of_week=payload.day_of_week,
        start_time=payload.start_time,
        end_time=payload.end_time,
    )

    return create_provider_break(
        db=db,
        provider_id=provider_id,
        break_data=payload,
    )


@router.get(
    "/{provider_id}/breaks",
    response_model=list[ProviderBreakResponse],
)
def list_breaks_for_provider(
    provider_id: UUID,
    db: Annotated[Session, Depends(get_db)],
):
    get_provider_or_404(provider_id, db)

    return get_provider_breaks(
        db=db,
        provider_id=provider_id,
    )


@router.put(
    "/{provider_id}/breaks/{break_id}",
    response_model=ProviderBreakResponse,
)
def update_break_for_provider(
    provider_id: UUID,
    break_id: UUID,
    payload: ProviderBreakUpdate,
    db: Annotated[Session, Depends(get_db)],
):
    get_provider_or_404(provider_id, db)

    provider_break = get_provider_break(
        db=db,
        provider_id=provider_id,
        break_id=break_id,
    )

    if provider_break is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Break not found",
        )

    final_day_of_week = (
        payload.day_of_week
        if payload.day_of_week is not None
        else provider_break.day_of_week
    )

    final_start_time = (
        payload.start_time
        if payload.start_time is not None
        else provider_break.start_time
    )

    final_end_time = (
        payload.end_time if payload.end_time is not None else provider_break.end_time
    )

    if final_start_time >= final_end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_time must be before end_time",
        )

    validate_break_overlap(
        db=db,
        provider_id=provider_id,
        day_of_week=final_day_of_week,
        start_time=final_start_time,
        end_time=final_end_time,
        exclude_break_id=break_id,
    )

    return update_provider_break(
        db=db,
        provider_break=provider_break,
        break_data=payload,
    )


@router.delete(
    "/{provider_id}/breaks/{break_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_break_for_provider(
    provider_id: UUID,
    break_id: UUID,
    db: Annotated[Session, Depends(get_db)],
):
    get_provider_or_404(provider_id, db)

    provider_break = get_provider_break(
        db=db,
        provider_id=provider_id,
        break_id=break_id,
    )

    if provider_break is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Break not found",
        )

    delete_provider_break(
        db=db,
        provider_break=provider_break,
    )


@router.post("/{provider_id}/availability", response_model=ScheduleResponse)
def set_provider_availability(
    provider_id: UUID,
    payload: AvailabilityRequest,
    db: Annotated[Session, Depends(get_db)],
):
    provider = get_provider_or_404(provider_id, db)
    provider = replace_provider_availability(db, provider, payload)
    return build_schedule(provider, None)


@router.get(
    "/{provider_id}/unavailability",
    response_model=list[BlackoutResponse],
)
def list_provider_unavailability(
    provider_id: UUID,
    db: Annotated[Session, Depends(get_db)],
):
    get_provider_or_404(provider_id, db)
    return [
        blackout_item_response(item)
        for item in list_provider_blackouts(db, provider_id)
    ]


@router.post(
    "/{provider_id}/unavailability",
    response_model=BlackoutResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_provider_unavailability(
    provider_id: UUID,
    payload: UnavailabilityRequest,
    db: Annotated[Session, Depends(get_db)],
):
    get_provider_or_404(provider_id, db)
    return blackout_item_response(create_provider_blackout(db, provider_id, payload))


@router.delete(
    "/{provider_id}/unavailability/{blackout_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_provider_unavailability(
    provider_id: UUID,
    blackout_id: UUID,
    db: Annotated[Session, Depends(get_db)],
):
    get_provider_or_404(provider_id, db)
    if not delete_provider_blackout(db, provider_id, blackout_id):
        raise HTTPException(status_code=404, detail="Unavailability not found")


@router.get("/{provider_id}/schedule", response_model=ScheduleResponse)
def get_provider_schedule(
    provider_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    schedule_date: Annotated[date | None, Query(alias="date")] = None,
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
