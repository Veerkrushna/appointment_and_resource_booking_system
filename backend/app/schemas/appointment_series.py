from datetime import UTC, date, datetime, time
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.models.appointment import AppointmentStatus
from app.models.appointment_series import (
    AppointmentSeriesEndMode,
    AppointmentSeriesFrequency,
    AppointmentSeriesStatus,
)


class AppointmentSeriesCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: UUID
    provider_id: UUID
    start_date: date
    local_start_time: time
    frequency: AppointmentSeriesFrequency
    interval: int = Field(strict=True, ge=1)
    end_mode: AppointmentSeriesEndMode
    occurrence_count: int | None = Field(default=None, strict=True)
    end_date: date | None = None
    user_name: str = Field(min_length=1, max_length=255)
    user_email: EmailStr
    user_phone: str | None = Field(default=None, max_length=30)
    notes: str | None = None

    @field_validator("frequency", mode="before")
    @classmethod
    def normalize_frequency(cls, value):
        if isinstance(value, str):
            try:
                return AppointmentSeriesFrequency[value.upper()]
            except KeyError:
                return value
        return value

    @field_validator("end_mode", mode="before")
    @classmethod
    def normalize_end_mode(cls, value):
        if isinstance(value, str):
            try:
                return AppointmentSeriesEndMode[value.upper()]
            except KeyError:
                return value
        return value

    @field_validator("local_start_time")
    @classmethod
    def require_naive_local_time(cls, value: time) -> time:
        if value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError("local_start_time must not include a timezone")
        return value

    @model_validator(mode="after")
    def validate_recurrence_rule(self):
        if self.frequency == AppointmentSeriesFrequency.WEEKLY:
            if self.interval not in (1, 2):
                raise ValueError("WEEKLY interval must be 1 or 2")
        elif self.interval != 1:
            raise ValueError("MONTHLY interval must be 1")

        if self.end_mode == AppointmentSeriesEndMode.COUNT:
            if self.occurrence_count is None:
                raise ValueError("COUNT end mode requires occurrence_count")
            if not 1 <= self.occurrence_count <= 52:
                raise ValueError("occurrence_count must be between 1 and 52")
            if self.end_date is not None:
                raise ValueError("COUNT end mode cannot include end_date")
        else:
            if self.end_date is None:
                raise ValueError("END_DATE end mode requires end_date")
            if self.occurrence_count is not None:
                raise ValueError("END_DATE end mode cannot include occurrence_count")
            if self.end_date < self.start_date:
                raise ValueError("end_date cannot be before start_date")
        return self


class AppointmentSeriesOccurrenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    occurrence_number: int
    appointment_start: datetime
    appointment_end: datetime
    status: AppointmentStatus

    @field_serializer("appointment_start", "appointment_end")
    def serialize_utc(self, value: datetime) -> datetime:
        return value.astimezone(UTC)


class AppointmentSeriesCancellationResponse(BaseModel):
    series_id: UUID
    status: AppointmentSeriesStatus
    appointments_cancelled: int
    cancelled_appointment_ids: list[UUID]


class AppointmentSeriesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    service_id: UUID
    provider_id: UUID
    frequency: AppointmentSeriesFrequency
    interval: int
    start_date: date
    local_start_time: time
    timezone: str
    end_mode: AppointmentSeriesEndMode
    occurrence_count: int | None
    end_date: date | None
    status: AppointmentSeriesStatus
    occurrences: list[AppointmentSeriesOccurrenceResponse]


class AppointmentSeriesDetailResponse(BaseModel):
    series_id: UUID
    service_id: UUID
    provider_id: UUID
    frequency: AppointmentSeriesFrequency
    interval: int
    start_date: date
    local_start_time: time
    provider_timezone: str
    end_mode: AppointmentSeriesEndMode
    occurrence_count: int | None
    end_date: date | None
    status: AppointmentSeriesStatus
    occurrences: list[AppointmentSeriesOccurrenceResponse]
