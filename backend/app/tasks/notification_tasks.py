import logging
from datetime import UTC, datetime, timedelta
from threading import Thread

from sqlalchemy import select

from app.celery_app import celery_app
from app.core.config import settings
from app.db.database import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.services.notifications import deliver_notification


def _schedule(task, appointment: Appointment, eta: datetime) -> None:
    if eta > datetime.now(UTC):

        def enqueue() -> None:
            try:
                task.apply_async(args=[str(appointment.id)], eta=eta, retry=False)
            except Exception:
                logging.getLogger(__name__).exception(
                    "Unable to schedule notification for appointment %s",
                    appointment.id,
                )

        Thread(target=enqueue, daemon=True).start()


def schedule_appointment_notifications(appointment: Appointment) -> None:
    _schedule(
        send_email_reminder,
        appointment,
        appointment.appointment_start - timedelta(hours=24),
    )
    _schedule(
        send_sms_reminder,
        appointment,
        appointment.appointment_start - timedelta(hours=1),
    )
    _schedule(
        send_feedback_request,
        appointment,
        appointment.appointment_end
        + timedelta(minutes=settings.feedback_delay_minutes),
    )


def _send_once(
    appointment_id: str,
    notification_type: NotificationType,
    recipient_email: str | None,
    recipient_phone: str | None,
) -> bool:
    with SessionLocal() as db:
        appointment = db.get(Appointment, appointment_id)

        if appointment is None or appointment.status == AppointmentStatus.CANCELLED:
            return False

        notification = db.scalar(
            select(Notification)
            .where(
                Notification.appointment_id == appointment.id,
                Notification.notification_type == notification_type,
                Notification.recipient_email == recipient_email,
                Notification.recipient_phone == recipient_phone,
            )
            .order_by(Notification.created_at.desc())
        )

        if notification is not None:
            if notification.status == NotificationStatus.SENT:
                return True
        else:
            notification = Notification(
                appointment_id=appointment.id,
                notification_type=notification_type,
                recipient_email=recipient_email,
                recipient_phone=recipient_phone,
            )
            db.add(notification)
            db.commit()

        return deliver_notification(db, notification, appointment)


@celery_app.task(
    name="appointments.send_email_reminder",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_kwargs={"max_retries": 3},
)
def send_email_reminder(appointment_id: str) -> None:
    with SessionLocal() as db:
        appointment = db.get(Appointment, appointment_id)

        if appointment is not None:
            delivered = _send_once(
                appointment_id,
                NotificationType.REMINDER,
                appointment.user_email,
                None,
            )

            if not delivered:
                raise RuntimeError("Email reminder delivery failed")


@celery_app.task(
    name="appointments.send_sms_reminder",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_kwargs={"max_retries": 3},
)
def send_sms_reminder(appointment_id: str) -> None:
    with SessionLocal() as db:
        appointment = db.get(Appointment, appointment_id)

        if appointment is not None and appointment.user_phone:
            delivered = _send_once(
                appointment_id,
                NotificationType.REMINDER,
                None,
                appointment.user_phone,
            )

            if not delivered:
                raise RuntimeError("SMS reminder delivery failed")


@celery_app.task(
    name="appointments.send_feedback_request",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_kwargs={"max_retries": 3},
)
def send_feedback_request(appointment_id: str) -> None:
    with SessionLocal() as db:
        appointment = db.get(Appointment, appointment_id)

        if appointment is not None:
            delivered = _send_once(
                appointment_id,
                NotificationType.FEEDBACK_REQUEST,
                appointment.user_email,
                None,
            )

            if not delivered:
                raise RuntimeError("Feedback request delivery failed")
