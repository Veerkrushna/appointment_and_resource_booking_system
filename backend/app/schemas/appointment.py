from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.timezones import to_local
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
    model_config = ConfigDict(extra="forbid")

    cancelled_by: str = Field(default="customer", min_length=1, max_length=100)
    reason: str | None = None


class AppointmentCancellationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    appointment_id: UUID
    cancelled_by: str
    reason: str | None
    refund_status: RefundStatus
    cancelled_at: datetime


class AppointmentRescheduleCreate(BaseModel):
    appointment_start: datetime
    cancelled_by: str = Field(min_length=1, max_length=100)
    reason: str | None = None
    refund_status: RefundStatus = RefundStatus.NOT_ELIGIBLE


AppointmentCancellationRequest = AppointmentCancellationCreate


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

    @classmethod
    def from_appointment(cls, appointment, timezone: str):
        from app.services.booking import get_booking_status

        response = cls.model_validate(appointment)

        now_utc = datetime.now(UTC)
        response.status = get_booking_status(
            appointment.appointment_start,
            appointment.duration_minutes,
            appointment.status,
            now_utc,
        )

        response.appointment_start = to_local(response.appointment_start, timezone)
        response.appointment_end = to_local(response.appointment_end, timezone)

        return response


class AppointmentListResponse(BaseModel):
    appointments: list[AppointmentResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class CustomerAppointmentResponse(AppointmentResponse):
    series_id: UUID | None = None
    occurrence_number: int | None = None
    payment_status: str | None = None

    @classmethod
    def from_appointment(cls, appointment, timezone: str):
        response = AppointmentResponse.from_appointment(appointment, timezone)

        return cls.model_validate(
            {
                **response.model_dump(),
                "series_id": appointment.series_id,
                "occurrence_number": appointment.occurrence_number,
                "payment_status": (
                    appointment.payment.status.value
                    if appointment.payment is not None
                    else None
                ),
            }
        )


class CustomerAppointmentListResponse(AppointmentListResponse):
    appointments: list[CustomerAppointmentResponse]
