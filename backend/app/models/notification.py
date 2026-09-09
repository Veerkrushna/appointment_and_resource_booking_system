import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.appointment import Appointment


class NotificationType(enum.StrEnum):
    CONFIRMATION = "confirmation"
    REMINDER = "reminder"
    CANCELLATION = "cancellation"


class NotificationStatus(enum.StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class Notification(Base):
    """Tracks an email or SMS notification for an appointment."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    appointment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        SQLEnum(NotificationType, name="notification_type"), nullable=False
    )
    recipient_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    recipient_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[NotificationStatus] = mapped_column(
        SQLEnum(NotificationStatus, name="notification_status"),
        default=NotificationStatus.PENDING,
        server_default="PENDING",
        nullable=False,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    appointment: Mapped["Appointment"] = relationship(
        back_populates="notifications"
    )