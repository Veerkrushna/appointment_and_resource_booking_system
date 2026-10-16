import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.appointment_series import AppointmentSeries
    from app.models.booking_hold import BookingHold
    from app.models.refund import Refund
    from app.models.user import User


class PaymentStatus(enum.StrEnum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"


class PaymentProvider(enum.StrEnum):
    RAZORPAY = "RAZORPAY"


class PaymentWebhookEventStatus(enum.StrEnum):
    RECEIVED = "RECEIVED"
    RETRYABLE = "RETRYABLE"
    PROCESSED = "PROCESSED"
    IGNORED = "IGNORED"
    FAILED = "FAILED"


class PaymentWebhookCaptureValidationFailure(enum.StrEnum):
    INVALID_PAYMENT_ID = "invalid_payment_id"
    INVALID_CAPTURE_STATUS = "invalid_capture_status"
    PROVIDER_ORDER_ID_MISMATCH = "provider_order_id_mismatch"
    PROVIDER_PAYMENT_ID_MISMATCH = "provider_payment_id_mismatch"
    INVALID_AMOUNT = "invalid_amount"
    AMOUNT_MISMATCH = "amount_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "appointment_id IS NULL OR series_id IS NULL",
            name="ck_payments_not_both_appointment_and_series",
        ),
        UniqueConstraint("appointment_id", name="uq_payments_appointment_id"),
        UniqueConstraint("series_id", name="uq_payments_series_id"),
        UniqueConstraint("provider_order_id", name="uq_payments_provider_order_id"),
        Index("ix_payments_customer_id", "customer_id"),
        Index("ix_payments_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("appointments.id"), nullable=True
    )
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("appointment_series.id"), nullable=True
    )
    # Monetary amounts use paise, the smallest INR unit.
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), default="INR", server_default="INR", nullable=False
    )
    status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(PaymentStatus, name="payment_status"), nullable=False
    )
    provider: Mapped[PaymentProvider] = mapped_column(
        SQLEnum(PaymentProvider, name="payment_provider"), nullable=False
    )
    provider_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_signature: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    customer: Mapped["User"] = relationship(back_populates="payments")
    appointment: Mapped["Appointment | None"] = relationship(back_populates="payment")
    series: Mapped["AppointmentSeries | None"] = relationship(back_populates="payment")
    booking_holds: Mapped[list["BookingHold"]] = relationship(back_populates="payment")
    refunds: Mapped[list["Refund"]] = relationship(back_populates="payment")


class PaymentWebhookEvent(Base):
    __tablename__ = "payment_webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "provider_event_id",
            name="uq_payment_webhook_events_provider_event_id",
        ),
        Index("ix_payment_webhook_events_status", "status"),
        Index("ix_payment_webhook_events_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_refund_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    capture_validation_failure: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    capture_validation_details: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True
    )
    local_payment_state_conflict: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    status: Mapped[PaymentWebhookEventStatus] = mapped_column(
        SQLEnum(PaymentWebhookEventStatus, name="payment_webhook_event_status"),
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
