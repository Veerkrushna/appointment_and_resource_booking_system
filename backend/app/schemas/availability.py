from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AvailabilitySlot(BaseModel):
    provider_id: UUID
    provider_name: str
    service_id: UUID
    date: date
    start: datetime
    end: datetime
    duration_minutes: int


class AvailabilitySlotsResponse(BaseModel):
    slots: list[AvailabilitySlot]

    page: int
    page_size: int
    total: int
    total_pages: int


class AvailabilitySlotsQuery(BaseModel):
    service_id: UUID | None = None
    provider_id: UUID | None = None
    start_date: date
    end_date: date
    page: int = Field(default=1, ge=1)
