import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.appointment import Appointment


class RefundStatus(enum.StrEnum):
    PENDING = "pending"
    REFUNDED = "refunded"
    NOT_ELIGIBLE = "not_eligible"


class AppointmentCancellation(Base):
    """Records why and how an appointment was cancelled."""

    __tablename__ = "appointment_cancellations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Keep cancellation history tied to the appointment, and remove it when
    # the parent appointment is permanently deleted.
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False
    )
    cancelled_by: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    refund_status: Mapped[RefundStatus] = mapped_column(
        SQLEnum(RefundStatus, name="refund_status"), nullable=False
    )
    cancelled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    appointment: Mapped["Appointment"] = relationship(
        back_populates="cancellations"
    )