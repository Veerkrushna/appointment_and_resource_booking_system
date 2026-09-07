import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.service import ServiceStatus


class ServiceCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=255,
        examples=["Doctor Consultation"],
    )

    description: str | None = Field(
        default=None,
        max_length=1000,
        examples=["A 30-minute consultation with a doctor."],
    )

    duration_minutes: int = Field(
        gt=0,
        examples=[30],
    )

    price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=10,
        decimal_places=2,
        examples=[500.00],
    )

    category: str = Field(
        min_length=1,
        max_length=100,
        examples=["Medical"],
    )

    capacity: int = Field(
        default=1,
        gt=0,
        examples=[1],
    )

    buffer_time_minutes: int | None = Field(
        default=None,
        ge=0,
        examples=[10],
    )

    status: ServiceStatus = ServiceStatus.ACTIVE


class ServiceUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    description: str | None = Field(
        default=None,
        max_length=1000,
    )

    duration_minutes: int | None = Field(
        default=None,
        gt=0,
    )

    price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=10,
        decimal_places=2,
    )

    category: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    capacity: int | None = Field(
        default=None,
        gt=0,
    )

    buffer_time_minutes: int | None = Field(
        default=None,
        ge=0,
    )

    status: ServiceStatus | None = None


class ServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID

    name: str

    description: str | None

    duration_minutes: int

    price: Decimal | None

    category: str

    capacity: int

    buffer_time_minutes: int | None

    status: ServiceStatus

    created_at: datetime

    updated_at: datetime
