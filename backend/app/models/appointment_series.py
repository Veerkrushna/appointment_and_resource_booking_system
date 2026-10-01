import enum
import uuid
from datetime import date, datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.providers import Provider
    from app.models.service import Service
    from app.models.user import User


class AppointmentSeriesFrequency(enum.StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class AppointmentSeriesEndMode(enum.StrEnum):
    COUNT = "count"
    END_DATE = "end_date"


class AppointmentSeriesStatus(enum.StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"


class AppointmentSeries(Base):
    __tablename__ = "appointment_series"
    __table_args__ = (
        CheckConstraint(
            "occurrence_count IS NULL OR occurrence_count BETWEEN 1 AND 52",
            name="ck_appointment_series_occurrence_count_range",
        ),
        CheckConstraint(
            "(end_mode = 'COUNT' AND occurrence_count IS NOT NULL AND end_date IS NULL) "
            "OR (end_mode = 'END_DATE' AND occurrence_count IS NULL AND end_date IS NOT NULL)",
            name="ck_appointment_series_end_condition",
        ),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_appointment_series_end_date_after_start",
        ),
        CheckConstraint(
            "(frequency = 'WEEKLY' AND interval IN (1, 2)) "
            "OR (frequency = 'MONTHLY' AND interval = 1)",
            name="ck_appointment_series_frequency_interval",
        ),
        Index("ix_appointment_series_customer_id", "customer_id"),
        Index("ix_appointment_series_provider_start", "provider_id", "start_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            name="fk_appointment_series_customer_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "providers.id",
            name="fk_appointment_series_provider_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "services.id",
            name="fk_appointment_series_service_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    frequency: Mapped[AppointmentSeriesFrequency] = mapped_column(
        SQLEnum(AppointmentSeriesFrequency, name="appointment_series_frequency"),
        nullable=False,
    )
    interval: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    local_start_time: Mapped[time] = mapped_column(Time, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    end_mode: Mapped[AppointmentSeriesEndMode] = mapped_column(
        SQLEnum(AppointmentSeriesEndMode, name="appointment_series_end_mode"),
        nullable=False,
    )
    occurrence_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[AppointmentSeriesStatus] = mapped_column(
        SQLEnum(AppointmentSeriesStatus, name="appointment_series_status"),
        default=AppointmentSeriesStatus.ACTIVE,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    customer: Mapped["User | None"] = relationship(back_populates="appointment_series")
    provider: Mapped["Provider"] = relationship()
    service: Mapped["Service"] = relationship()
    appointments: Mapped[list["Appointment"]] = relationship(
        back_populates="series", passive_deletes="all"
    )
