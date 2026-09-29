import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.providers import Provider
    from app.models.review import Review


class UserRole(enum.StrEnum):
    CUSTOMER = "CUSTOMER"
    PROVIDER = "PROVIDER"
    ADMIN = "ADMIN"
    SERVICE_PROVIDER = "PROVIDER"

    @classmethod
    def _missing_(cls, value):
        if not isinstance(value, str):
            return None

        normalized = value.strip()
        if not normalized:
            return None

        upper = normalized.upper()
        if upper == "SERVICE_PROVIDER":
            return cls.PROVIDER
        if upper in cls._value2member_map_:
            return cls(upper)

        lowered = normalized.lower()
        if lowered in {"customer", "provider", "admin"}:
            return cls(lowered.upper())

        return None


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), default=UserRole.CUSTOMER, nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    created_by_user: Mapped["User | None"] = relationship(
        remote_side=[id], back_populates="created_users"
    )
    created_users: Mapped[list["User"]] = relationship(back_populates="created_by_user")
    appointments = relationship("Appointment", back_populates="customer")
    provider_profile: Mapped["Provider | None"] = relationship(back_populates="user")
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="customer", cascade="all, delete", passive_deletes=True
    )
