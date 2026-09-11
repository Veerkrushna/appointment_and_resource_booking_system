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
    start_date: Annotated[
        date,
        Query(description="Start date in YYYY-MM-DD format"),
    ],
    end_date: Annotated[
        date,
        Query(description="End date in YYYY-MM-DD format"),
    ],
    service_id: Annotated[
        UUID | None,
        Query(description="Optional service UUID"),
    ] = None,
    provider_id: Annotated[
        UUID | None,
        Query(description="Optional provider UUID"),
    ] = None,
    page: Annotated[
        int,
        Query(ge=1, description="Page number"),
    ] = 1,
    slot_interval_minutes: Annotated[
        int,
        Query(ge=1, le=120),
    ] = 15,
):
    # Validate date range
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be before or equal to end_date",
        )

    # Limit date range to 31 days
    if (end_date - start_date).days > 31:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date range cannot exceed 31 days",
        )

    # Calculate availability
    result = calculate_available_slots(
        db=db,
        service_id=service_id,
        start_date=start_date,
        end_date=end_date,
        provider_id=provider_id,
        slot_interval_minutes=slot_interval_minutes,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active services found",
        )

    # Pagination
    page_size = 20
    total = len(result)

    start_index = (page - 1) * page_size
    end_index = start_index + page_size

    paginated_slots = result[start_index:end_index]

    total_pages = (total + page_size - 1) // page_size

    return AvailabilitySlotsResponse(
        slots=paginated_slots,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )
