# FastAPI dependencies are intentionally declared in function signatures.
# ruff: noqa: B008
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.availability import AvailabilitySlotsResponse
from app.services.availability import calculate_available_slots

router = APIRouter(prefix="/api/availability", tags=["Availability"])


@router.get("/slots", response_model=AvailabilitySlotsResponse)
def get_available_slots(
    db: Session = Depends(get_db),
    service_id: UUID = Query(..., description="Service UUID"),
    date: date = Query(..., description="Date in YYYY-MM-DD format"),
    provider_id: UUID | None = Query(default=None, description="Optional provider UUID"),
    slot_interval_minutes: int = Query(default=15, ge=1, le=120),
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
