from sqlalchemy import func, literal_column

from app.models.appointment import Appointment
from app.models.service import Service


def appointment_blocked_interval():
    buffer_interval = func.coalesce(Service.buffer_time_minutes, 0) * literal_column(
        "INTERVAL '1 minute'"
    )
    return (
        Appointment.appointment_start,
        Appointment.appointment_end + buffer_interval,
    )
