import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.payment import Payment
    from app.models.providers import Provider
    from app.models.service import Service
    from app.models.user import User


class BookingHoldStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    CONVERTED = "CONVERTED"
    EXPIRED = "EXPIRED"
    RELEASED = "RELEASED"


class BookingHold(Base):
    __tablename__ = "booking_holds"
    __table_args__ = (
        Index("ix_booking_holds_provider_id", "provider_id"),
        Index("ix_booking_holds_appointment_start", "appointment_start"),
        Index("ix_booking_holds_appointment_end", "appointment_end"),
        Index("ix_booking_holds_expires_at", "expires_at"),
        Index("ix_booking_holds_status", "status"),
        Index("ix_booking_holds_payment_id", "payment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
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
    appointment_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    appointment_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[BookingHoldStatus] = mapped_column(
        SQLEnum(BookingHoldStatus, name="booking_hold_status"), nullable=False
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payments.id"), nullable=True
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

    customer: Mapped["User"] = relationship(back_populates="booking_holds")
    service: Mapped["Service"] = relationship(back_populates="booking_holds")
    provider: Mapped["Provider"] = relationship(back_populates="booking_holds")
    payment: Mapped["Payment | None"] = relationship(back_populates="booking_holds")
