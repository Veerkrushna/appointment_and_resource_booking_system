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
    service_id: UUID
    date: date
    slot_interval_minutes: int
    slots: list[AvailabilitySlot]


class AvailabilitySlotsQuery(BaseModel):
    service_id: UUID
    date: date
    provider_id: UUID | None = None
    slot_interval_minutes: int = Field(default=15, ge=1, le=120)
