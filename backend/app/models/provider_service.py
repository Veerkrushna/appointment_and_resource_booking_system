import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.providers import Provider
    from app.models.service import Service


class ProviderService(Base):
    """Associates a provider or resource with a service they can offer."""

    __tablename__ = "provider_services"
    __table_args__ = (
        UniqueConstraint(
            "provider_id", "service_id", name="uq_provider_service"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )

    # Deactivating this row removes the service from new booking choices
    # without deleting the provider's historical relationship.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    provider: Mapped["Provider"] = relationship(back_populates="service_links")
    service: Mapped["Service"] = relationship(back_populates="provider_links")