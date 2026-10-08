from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AppointmentPaymentOrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: UUID
    provider_id: UUID
    appointment_start: datetime


class PaymentOrderResponse(BaseModel):
    payment_id: UUID
    key_id: str
    order_id: str
    amount: int = Field(gt=0)
    currency: str
    hold_expires_at: datetime
