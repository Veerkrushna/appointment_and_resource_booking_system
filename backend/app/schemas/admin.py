from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.appointment import AppointmentResponse
from app.schemas.providers import (
    AvailabilityWindow,
    BlackoutResponse,
    BreakWindow,
    ProviderResponse,
)


class AdminAppointmentResponse(AppointmentResponse):
    provider_name: str
    service_name: str

    @classmethod
    def from_records(cls, appointment, provider_name: str, service_name: str, timezone: str):
        appointment_response = AppointmentResponse.from_appointment(appointment, timezone)
        return cls(
            **appointment_response.model_dump(),
            provider_name=provider_name,
            service_name=service_name,
        )


class AppointmentStatusCount(BaseModel):
    status: str
    count: int


class AdminOverviewResponse(BaseModel):
    generated_at: datetime
    timezone: str
    total_appointments: int
    upcoming_appointments: int
    appointments_today: int
    appointments_by_status: list[AppointmentStatusCount]
    total_providers: int
    active_providers: int
    total_services: int
    active_services: int


class AdminAppointmentListResponse(BaseModel):
    appointments: list[AdminAppointmentResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class ProviderScheduleResponse(BaseModel):
    provider: ProviderResponse
    timezone: str
    start_date: date
    end_date: date
    availability: list[AvailabilityWindow]
    breaks: list[BreakWindow]
    blackout_dates: list[BlackoutResponse]
    appointments: list[AdminAppointmentResponse]