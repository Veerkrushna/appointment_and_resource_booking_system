from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

class Service(Base):

    """
    A Service is something a customer can book — e.g. 'Haircut',
    'Consultation', '30-min Yoga Session'. It has a fixed duration
    and price, and is the entity that Bookings will eventually
    reference.
    """

    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String(255), nullable = False)

    description: Mapped[str | None] = mapped_column(String(1000), nullable = True)

    # Stored in minutes. Availability calculation (working hours minus
    # existing bookings) will use this to figure out how long a slot
    # needs to be reserved for.
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable = False)

    # Numeric (not Float) is used for money to avoid floating-point
    # rounding errors. precision=10, scale=2 means up to 8 digits
    # before the decimal and 2 after (e.g. 99999999.99).
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    # Soft-disable flag: lets us stop a service from being bookable
    # without deleting historical data tied to it (past bookings still
    # need to reference the service that existed at the time).
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

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