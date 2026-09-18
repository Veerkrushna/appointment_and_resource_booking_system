from datetime import UTC, datetime

from sqlalchemy import select

from app.celery_app import celery_app
from app.db.database import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus


@celery_app.task(
    name="appointments.complete_expired_appointments",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_kwargs={"max_retries": 3},
)
def complete_expired_appointments() -> int:
    db = SessionLocal()
    try:
        now_utc = datetime.now(UTC)
        appointments = db.scalars(
            select(Appointment).where(
                Appointment.status.in_(
                    [AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]
                ),
                Appointment.appointment_end <= now_utc,
            )
        ).all()

        for appointment in appointments:
            appointment.status = AppointmentStatus.COMPLETED

        if appointments:
            db.commit()

        return len(appointments)
    finally:
        db.close()
