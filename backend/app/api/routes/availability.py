from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.availability import AvailabilitySlotsResponse
from app.services.availability import calculate_available_slots

router = APIRouter(prefix="/api/availability", tags=["Availability"])


@router.get("/slots", response_model=AvailabilitySlotsResponse)
def get_available_slots(
    db: Annotated[Session, Depends(get_db)],
    service_id: Annotated[UUID, Query(description="Service UUID")],
    date: Annotated[date, Query(description="Date in YYYY-MM-DD format")],
    provider_id: Annotated[
        UUID | None, Query(description="Optional provider UUID")
    ] = None,
    slot_interval_minutes: Annotated[int, Query(ge=1, le=120)] = 15,
):
    result = calculate_available_slots(
        db,
        service_id,
        date,
        provider_id,
        slot_interval_minutes,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active service not found",
        )
    return result
