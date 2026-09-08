from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.providers import AvailabilityStatus, ProviderType


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: ProviderType
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)
    availability_status: AvailabilityStatus = AvailabilityStatus.AVAILABLE


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    type: ProviderType | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    availability_status: AvailabilityStatus | None = None


class ProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    type: ProviderType
    email: str
    phone: str | None
    availability_status: AvailabilityStatus
    created_at: datetime


class AvailabilityWindow(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None
    is_working_day: bool = True

    @model_validator(mode="after")
    def validate_window(self):
        if self.is_working_day:
            if self.start_time is None or self.end_time is None:
                raise ValueError("working days require both start_time and end_time")
            if self.start_time >= self.end_time:
                raise ValueError("start_time must be before end_time")
        elif self.start_time is not None or self.end_time is not None:
            raise ValueError("non-working days cannot have working hours")
        return self


class BreakWindow(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    break_type: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_window(self):
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class ProviderBreakCreate(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    break_type: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_window(self):
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class ProviderBreakUpdate(BaseModel):
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None
    break_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )


class ProviderBreakResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_id: UUID
    day_of_week: int
    start_time: time
    end_time: time
    break_type: str


class BlackoutWindow(BaseModel):
    blackout_start: datetime
    blackout_end: datetime
    reason: str | None = Field(default=None, max_length=500)
    is_all_day: bool = False

    @model_validator(mode="after")
    def validate_window(self):
        if self.blackout_start >= self.blackout_end:
            raise ValueError("blackout_start must be before blackout_end")
        return self


class BlackoutResponse(BlackoutWindow):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class UnavailabilityRequest(BaseModel):
    start_date: date
    end_date: date
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


class AvailabilityRequest(BaseModel):
    availability: list[AvailabilityWindow] = Field(default_factory=list)
    breaks: list[BreakWindow] = Field(default_factory=list)
    blackout_dates: list[BlackoutWindow] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_days(self):
        days = [window.day_of_week for window in self.availability]
        if len(days) != len(set(days)):
            raise ValueError("availability can contain only one window per day")
        return self


class ScheduleResponse(BaseModel):
    provider: ProviderResponse
    date: date | None
    availability: list[AvailabilityWindow]
    breaks: list[BreakWindow]
    blackout_dates: list[BlackoutWindow]

    blackout_dates: list[BlackoutResponse]
