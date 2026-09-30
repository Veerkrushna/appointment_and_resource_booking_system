import pytest
from datetime import datetime, UTC

from app.models.appointment import AppointmentStatus
from app.services.booking import get_booking_status, can_modify_booking

def test_booking_rules():
    # 2:00 PM booking, 30 min duration
    appointment_start = datetime(2026, 10, 1, 14, 0, tzinfo=UTC)
    duration_minutes = 30
    
    # 11:59 AM -> allowed
    now = datetime(2026, 10, 1, 11, 59, tzinfo=UTC)
    assert can_modify_booking(appointment_start, now) is True
    assert get_booking_status(appointment_start, duration_minutes, AppointmentStatus.CONFIRMED, now) == "confirmed"

    # 12:00 PM -> blocked
    now = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    assert can_modify_booking(appointment_start, now) is False
    assert get_booking_status(appointment_start, duration_minutes, AppointmentStatus.CONFIRMED, now) == "confirmed"

    # 1:59 PM -> blocked
    now = datetime(2026, 10, 1, 13, 59, tzinfo=UTC)
    assert can_modify_booking(appointment_start, now) is False
    assert get_booking_status(appointment_start, duration_minutes, AppointmentStatus.CONFIRMED, now) == "confirmed"

    # 2:00 PM -> In progress, blocked
    now = datetime(2026, 10, 1, 14, 0, tzinfo=UTC)
    assert can_modify_booking(appointment_start, now) is False
    assert get_booking_status(appointment_start, duration_minutes, AppointmentStatus.CONFIRMED, now) == "in_progress"

    # 2:29 PM -> In progress, blocked
    now = datetime(2026, 10, 1, 14, 29, tzinfo=UTC)
    assert can_modify_booking(appointment_start, now) is False
    assert get_booking_status(appointment_start, duration_minutes, AppointmentStatus.CONFIRMED, now) == "in_progress"

    # 2:30 PM -> Completed, blocked
    now = datetime(2026, 10, 1, 14, 30, tzinfo=UTC)
    assert can_modify_booking(appointment_start, now) is False
    assert get_booking_status(appointment_start, duration_minutes, AppointmentStatus.CONFIRMED, now) == "completed"

    # Cancelled booking -> always "Cancelled"
    now = datetime(2026, 10, 1, 11, 0, tzinfo=UTC) # anytime
    assert get_booking_status(appointment_start, duration_minutes, AppointmentStatus.CANCELLED, now) == "cancelled"
