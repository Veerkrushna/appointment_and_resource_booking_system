from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.appointment import AppointmentStatus
from app.models.appointment_cancellation import RefundStatus


class AppointmentCreate(BaseModel):
    service_id: UUID
    provider_id: UUID
    user_name: str = Field(min_length=1, max_length=255)
    user_email: EmailStr
    user_phone: str | None = Field(default=None, max_length=30)
    appointment_start: datetime
    notes: str | None = None


class AppointmentUpdate(BaseModel):
    user_name: str | None = Field(default=None, min_length=1, max_length=255)
    user_email: EmailStr | None = None
    user_phone: str | None = Field(default=None, max_length=30)
    appointment_start: datetime | None = None
    notes: str | None = None
    status: AppointmentStatus | None = None


class AppointmentCancellationCreate(BaseModel):
    cancelled_by: str = Field(min_length=1, max_length=100)
    reason: str | None = None
    refund_status: RefundStatus = RefundStatus.PENDING


class AppointmentCancellationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    appointment_id: UUID
    cancelled_by: str
    reason: str | None
    refund_status: RefundStatus
    cancelled_at: datetime


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