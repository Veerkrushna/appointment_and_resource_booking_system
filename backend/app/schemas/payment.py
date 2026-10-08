from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.appointment import AppointmentStatus
from app.models.payment import PaymentStatus


class AppointmentPaymentOrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: UUID
    provider_id: UUID
    appointment_start: datetime
    user_name: str = Field(min_length=1, max_length=255)
    user_email: EmailStr
    user_phone: str | None = Field(default=None, max_length=30)
    notes: str | None = None


class PaymentOrderResponse(BaseModel):
    payment_id: UUID
    key_id: str
    order_id: str
    amount: int = Field(gt=0)
    currency: str
    hold_expires_at: datetime


class PaymentVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_id: UUID
    order_id: str = Field(min_length=1, max_length=255)
    provider_payment_id: str = Field(min_length=1, max_length=255)
    signature: str = Field(min_length=1, max_length=512)


class PaymentVerificationResponse(BaseModel):
    payment_id: UUID
    provider_payment_id: str
    order_id: str
    status: PaymentStatus
    appointment_id: UUID
    appointment_status: AppointmentStatus
    appointment_start: datetime
    appointment_end: datetime
