from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AppointmentCreate(BaseModel):
    service_id: UUID
    provider_id: UUID
    user_name: str = Field(min_length=1, max_length=255)
    user_email: EmailStr
    user_phone: str | None = Field(default=None, max_length=30)
    appointment_start: datetime
    notes: str | None = None


class AppointmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    service_id: UUID
    provider_id: UUID
    user_name: str
    user_email: EmailStr
    user_phone: str | None
    appointment_start: datetime
    appointment_end: datetime
    duration_minutes: int
    notes: str | None
    status: str