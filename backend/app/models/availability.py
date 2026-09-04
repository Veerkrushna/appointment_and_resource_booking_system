import uuid
from datetime import datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Time, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.providers import Provider


class ProviderAvailability(Base):
    # One row describes the normal working window for one weekday. A row with
    # is_working_day=False represents a regular day off for that provider.
    __tablename__ = "provider_availability"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Every schedule belongs to exactly one provider.
    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )

    # Store weekdays as 0-6 (Monday-Sunday) so slot calculation is consistent.
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    is_working_day: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    provider: Mapped["Provider"] = relationship(back_populates="availability")


class ProviderBreak(Base):
    # Breaks repeat weekly and are subtracted from the provider's working
    # window when available appointment slots are calculated.
    __tablename__ = "provider_breaks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )

    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    break_type: Mapped[str] = mapped_column(String(100), nullable=False)

    provider: Mapped["Provider"] = relationship(back_populates="breaks")


class ProviderBlackoutDate(Base):
    # Blackouts are date-specific exceptions such as holidays or extended
    # leave, so they use timezone-aware datetime boundaries.
    __tablename__ = "provider_blackout_dates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )

    blackout_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    blackout_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # When true, the interval represents a full unavailable day in the
    # provider's calendar; the boundaries still define the affected dates.
    is_all_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    provider: Mapped["Provider"] = relationship(back_populates="blackout_dates")