import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ServiceStatus(enum.StrEnum):
    """Matches the assignment's Status field: Active/Inactive."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class Service(Base):
    """
    A Service is something a customer can book — e.g. 'Haircut',
    'Consultation', '30-min Yoga Session'. It has a fixed duration
    and price, and is the entity that Appointments will reference.
    """

    __tablename__ = "services"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Stored in minutes. Availability calculation (working hours minus
    # existing bookings) will use this to figure out how long a slot
    # needs to be reserved for.
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    # Numeric (not Float) is used for money to avoid floating-point
    # rounding errors. precision=10, scale=2 means up to 8 digits
    # before the decimal and 2 after (e.g. 99999999.99). Optional per
    # spec — a service's price may not be finalized when it's created.
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    category: Mapped[str] = mapped_column(String(100), nullable=False)

    # Number of concurrent bookings allowed in the same slot, e.g. a
    # group fitness class. Defaults to 1 (the normal one-on-one case).
    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Gap enforced after an appointment of this service before the next
    # one can start. Feeds directly into the availability algorithm
    # (T13): working hours - bookings - breaks - blackout dates - buffer.
    buffer_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[ServiceStatus] = mapped_column(
        SQLEnum(ServiceStatus, name="service_status"),
        default=ServiceStatus.ACTIVE,
        nullable=False,
    )

    # server_default=func.now() means PostgreSQL itself sets this
    # value at insert time, not Python — so it's correct even if
    # multiple app instances have slightly different clocks.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Service id={self.id} name={self.name!r} status={self.status.value}>"
