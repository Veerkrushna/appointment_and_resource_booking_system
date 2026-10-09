import logging
from datetime import UTC, datetime, timedelta
from threading import Thread

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.celery_app import celery_app
from app.core.config import settings
from app.db.database import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.appointment_series import AppointmentSeries
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.services.notifications import (
    build_series_confirmation_email,
    deliver_email_notification,
    deliver_notification,
)

logger = logging.getLogger(__name__)


def _enqueue(task, appointment: Appointment, eta: datetime | None = None) -> None:
    appointment_id = str(appointment.id)

    def enqueue() -> None:
        try:
            if eta is None:
                task.delay(appointment_id)
            else:
                task.apply_async(args=[appointment_id], eta=eta, retry=False)
        except Exception:
            logger.exception(
                "Unable to enqueue notification for appointment %s", appointment_id
            )

    try:
        Thread(target=enqueue, daemon=True).start()
    except Exception:
        logger.exception(
            "Unable to start notification enqueue for appointment %s",
            appointment_id,
        )


def enqueue_confirmation_notification(appointment: Appointment) -> None:
    _enqueue(send_confirmation_notification, appointment)


def enqueue_series_confirmation_notification(series_id: str) -> None:
    def enqueue() -> None:
        try:
            send_series_confirmation_notification.delay(series_id)
        except Exception:
            logger.exception(
                "Unable to enqueue confirmation notification for series %s", series_id
            )

    try:
        Thread(target=enqueue, daemon=True).start()
    except Exception:
        logger.exception(
            "Unable to start confirmation notification enqueue for series %s",
            series_id,
        )


def _schedule(task, appointment: Appointment, eta: datetime) -> None:
    if eta > datetime.now(UTC):
        _enqueue(task, appointment, eta)


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
    *,
    lock_appointment: bool = False,
) -> bool:
    with SessionLocal() as db:
        if lock_appointment:
            appointment = db.scalar(
                select(Appointment)
                .where(Appointment.id == appointment_id)
                .with_for_update()
            )
        else:
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
            if not lock_appointment:
                db.commit()
            else:
                db.flush()

        return deliver_notification(db, notification, appointment)


@celery_app.task(
    name="appointments.send_confirmation_notification",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_kwargs={"max_retries": 3},
)
def send_confirmation_notification(appointment_id: str) -> None:
    with SessionLocal() as db:
        appointment = db.get(Appointment, appointment_id)
        if appointment is not None:
            _send_once(
                appointment_id,
                NotificationType.CONFIRMATION,
                appointment.user_email,
                None,
                lock_appointment=True,
            )


@celery_app.task(
    name="appointments.send_series_confirmation_notification",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_kwargs={"max_retries": 3},
)
def send_series_confirmation_notification(series_id: str) -> None:
    with SessionLocal() as db:
        series = db.scalar(
            select(AppointmentSeries)
            .options(
                selectinload(AppointmentSeries.appointments),
                selectinload(AppointmentSeries.service),
                selectinload(AppointmentSeries.provider),
            )
            .where(AppointmentSeries.id == series_id)
        )
        if series is None:
            logger.info(
                "Skipping confirmation for missing appointment series %s", series_id
            )
            return

        appointments = sorted(
            series.appointments,
            key=lambda appointment: appointment.occurrence_number or 0,
        )
        if not appointments:
            logger.warning(
                "Skipping confirmation for appointment series %s without occurrences",
                series_id,
            )
            return

        first_appointment = appointments[0]
        notification = db.scalar(
            select(Notification)
            .where(
                Notification.appointment_id == first_appointment.id,
                Notification.notification_type == NotificationType.CONFIRMATION,
                Notification.recipient_email == first_appointment.user_email,
                Notification.recipient_phone.is_(None),
            )
            .order_by(Notification.created_at.desc())
        )
        if notification is not None and notification.status == NotificationStatus.SENT:
            return
        if notification is None:
            notification = Notification(
                appointment_id=first_appointment.id,
                notification_type=NotificationType.CONFIRMATION,
                recipient_email=first_appointment.user_email,
            )
            db.add(notification)
            db.commit()

        subject, body = build_series_confirmation_email(series, appointments)
        delivered = deliver_email_notification(
            db,
            notification,
            first_appointment.user_email,
            subject,
            body,
        )
        if not delivered:
            raise RuntimeError("Recurring series confirmation delivery failed")


@celery_app.task(
    name="appointments.send_cancellation_notification",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_kwargs={"max_retries": 3},
)
def send_cancellation_notification(appointment_id: str) -> None:
    with SessionLocal() as db:
        appointment = db.get(Appointment, appointment_id)
        if appointment is None:
            return

        notification = Notification(
            appointment_id=appointment.id,
            notification_type=NotificationType.CANCELLATION,
            recipient_email=appointment.user_email,
        )
        db.add(notification)
        db.commit()
        deliver_notification(db, notification, appointment)


@celery_app.task(
    name="appointments.send_reschedule_notification",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_kwargs={"max_retries": 3},
)
def send_reschedule_notification(appointment_id: str) -> None:
    with SessionLocal() as db:
        appointment = db.get(Appointment, appointment_id)
        if appointment is None:
            return

        notification = Notification(
            appointment_id=appointment.id,
            notification_type=NotificationType.RESCHEDULE,
            recipient_email=appointment.user_email,
        )
        db.add(notification)
        db.commit()
        deliver_notification(db, notification, appointment)


@celery_app.task(
    name="appointments.send_confirmation_status_notification",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_kwargs={"max_retries": 3},
)
def send_confirmation_status_notification(appointment_id: str) -> None:
    with SessionLocal() as db:
        appointment = db.get(Appointment, appointment_id)
        if appointment is None:
            return

        notification = Notification(
            appointment_id=appointment.id,
            notification_type=NotificationType.CONFIRMATION,
            recipient_email=appointment.user_email,
        )
        db.add(notification)
        db.commit()
        deliver_notification(db, notification, appointment)


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
