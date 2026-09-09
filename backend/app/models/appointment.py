import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.appointment_cancellation import AppointmentCancellation
from app.models.notification import Notification

if TYPE_CHECKING:
    from app.models.providers import Provider
    from app.models.service import Service


class AppointmentStatus(enum.StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Appointment(Base):
    """A reservation connecting one customer, service, and provider."""

    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint(
            "appointment_end > appointment_start",
            name="ck_appointment_end_after_start",
        ),
        CheckConstraint(
            "duration_minutes > 0", name="ck_appointment_duration_positive"
        ),
        Index("ix_appointments_provider_start", "provider_id", "appointment_start"),
        Index("ix_appointments_user_email", "user_email"),
        Index("ix_appointments_status_start", "status", "appointment_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )

    user_name: Mapped[str] = mapped_column(String(255), nullable=False)
    user_email: Mapped[str] = mapped_column(String(320), nullable=False)
    user_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Store appointment instants as UTC-aware values. The API layer converts
    # from the user's timezone before saving and converts back for responses.
    appointment_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    appointment_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AppointmentStatus] = mapped_column(
        SQLEnum(AppointmentStatus, name="appointment_status"),
        default=AppointmentStatus.PENDING,
        nullable=False,
    )
    confirmation_token: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    service: Mapped["Service"] = relationship()
    provider: Mapped["Provider"] = relationship()
    cancellations: Mapped[list["AppointmentCancellation"]] = relationship(
        back_populates="appointment", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="appointment", cascade="all, delete-orphan"
    )
