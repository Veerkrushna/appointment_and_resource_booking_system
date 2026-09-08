import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.availability import (
        ProviderAvailability,
        ProviderBlackoutDate,
        ProviderBreak,
    )
    from app.models.provider_service import ProviderService


# Providers can be people who deliver services or physical resources that
# customers reserve, such as rooms or equipment.
class ProviderType(enum.StrEnum):
    PERSON = "person"
    RESOURCE = "resource"


class AvailabilityStatus(enum.StrEnum):
    # This is the provider's current high-level state. Detailed working hours
    # and exceptions are stored in the availability tables below.
    AVAILABLE = "available"
    ON_LEAVE = "on_leave"
    INACTIVE = "inactive"


class Provider(Base):
    # The provider is the parent record for schedules, breaks, and blackouts.
    __tablename__ = "providers"

    # SQLAlchemy generates a UUID in Python when a new provider is created.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    type: Mapped[ProviderType] = mapped_column(
        SQLEnum(ProviderType, name="provider_type"), nullable=False
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)

    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

    availability_status: Mapped[AvailabilityStatus] = mapped_column(
        SQLEnum(AvailabilityStatus, name="availability_status"), nullable=False
    )

    # PostgreSQL sets this timestamp when the row is inserted.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # These relationships expose each provider's scheduling rules and ensure
    # child records are removed when their provider is deleted.
    availability: Mapped[list["ProviderAvailability"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )
    breaks: Mapped[list["ProviderBreak"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )
    blackout_dates: Mapped[list["ProviderBlackoutDate"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )
    service_links: Mapped[list["ProviderService"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Provider id={self.id} name={self.name!r} "
            f"type={self.type.value} status={self.availability_status.value}>"
        )
