from sqlalchemy import literal_column

from app.models.appointment import Appointment


def appointment_blocked_interval():
    buffer_interval = Appointment.buffer_time_minutes * literal_column(
        "INTERVAL '1 minute'"
    )
    return (
        Appointment.appointment_start,
        Appointment.appointment_end + buffer_interval,
    )
