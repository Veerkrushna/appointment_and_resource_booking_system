import base64
import logging
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.appointment_series import AppointmentSeries
from app.models.notification import Notification, NotificationStatus, NotificationType

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, body: str) -> None:
    if not settings.smtp_host or not settings.smtp_from:
        raise RuntimeError("SMTP is not configured")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = to_email
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as client:
        if settings.smtp_starttls:
            client.starttls()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password or "")
        client.send_message(message)


def _send_email(appointment: Appointment, subject: str, body: str) -> None:
    send_email(appointment.user_email, subject, body)


def _send_sms(appointment: Appointment, body_text: str) -> None:
    if not appointment.user_phone:
        return
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise RuntimeError("SMS is not configured")
    if not settings.twilio_from_phone:
        raise RuntimeError("Twilio sender phone is not configured")
    body = urlencode(
        {
            "To": appointment.user_phone,
            "From": settings.twilio_from_phone,
            "Body": body_text,
        }
    ).encode()
    request = Request(
        "https://api.twilio.com/2010-04-01/Accounts/"
        f"{settings.twilio_account_sid}/Messages.json",
        data=body,
        method="POST",
    )
    credentials = f"{settings.twilio_account_sid}:{settings.twilio_auth_token}"
    request.add_header(
        "Authorization", "Basic " + base64.b64encode(credentials.encode()).decode()
    )
    with urlopen(request, timeout=10):
        pass


def _record_result(db: Session, notification: Notification, delivered: bool) -> None:
    notification.status = (
        NotificationStatus.SENT if delivered else NotificationStatus.FAILED
    )
    notification.retry_count += 1
    if delivered:
        notification.sent_at = datetime.now(UTC)
    db.commit()


def deliver_notification(
    db: Session, notification: Notification, appointment: Appointment
) -> None:
    is_email = notification.recipient_email is not None
    if notification.notification_type == NotificationType.CONFIRMATION:
        subject = "Appointment confirmation"
        body = (
            f"Hello {appointment.user_name},\n\n"
            "Your appointment has been confirmed.\n"
            f"Start: {appointment.appointment_start.isoformat()}\n"
            f"End: {appointment.appointment_end.isoformat()}\n\n"
            "Thank you."
        )
        sms_body = "Your appointment has been confirmed."
    elif notification.notification_type == NotificationType.REMINDER:
        subject = "Appointment reminder"
        body = (
            f"Hello {appointment.user_name},\n\n"
            "This is a reminder for your appointment at "
            f"{appointment.appointment_start.isoformat()}."
        )
        sms_body = "Reminder: your appointment is coming up soon."
    elif notification.notification_type == NotificationType.CANCELLATION:
        subject = "Appointment cancelled"
        body = f"Hello {appointment.user_name},\n\nYour appointment has been cancelled."
        sms_body = body
    elif notification.notification_type == NotificationType.RESCHEDULE:
        subject = "Appointment rescheduled"
        body = (
            f"Hello {appointment.user_name},\n\n"
            "Your appointment has been rescheduled.\n"
            f"New start: {appointment.appointment_start.isoformat()}"
        )
        sms_body = body
    else:
        subject = "How was your appointment?"
        body = (
            f"Hello {appointment.user_name},\n\n"
            "Please share your feedback about your recent appointment."
        )
        sms_body = body
    try:
        if is_email:
            _send_email(appointment, subject, body)
        else:
            _send_sms(appointment, sms_body)
    except Exception:
        logger.exception("Failed to send notification %s", notification.id)
        _record_result(db, notification, delivered=False)
    else:
        _record_result(db, notification, delivered=True)


def deliver_email_notification(
    db: Session,
    notification: Notification,
    recipient_email: str,
    subject: str,
    body: str,
) -> bool:
    try:
        send_email(recipient_email, subject, body)
    except Exception:
        logger.exception("Failed to send notification %s", notification.id)
        _record_result(db, notification, delivered=False)
        return False

    _record_result(db, notification, delivered=True)
    return True


def build_series_confirmation_email(
    series: AppointmentSeries, appointments: list[Appointment]
) -> tuple[str, str]:
    timezone = ZoneInfo(series.timezone)
    ordered_appointments = sorted(
        appointments, key=lambda appointment: appointment.occurrence_number or 0
    )
    if series.frequency.value == "weekly":
        recurrence_rule = "Every 2 weeks" if series.interval == 2 else "Every week"
    else:
        recurrence_rule = "Monthly"

    def format_appointment(appointment: Appointment) -> str:
        local_start = appointment.appointment_start.astimezone(timezone)
        date_label = (
            f"{local_start:%A}, {local_start:%B} {local_start.day}, {local_start:%Y}"
        )
        time_label = local_start.strftime("%I:%M %p").lstrip("0")
        return f"{date_label} — {time_label}"

    first_appointment = ordered_appointments[0]
    last_appointment = ordered_appointments[-1]
    schedule = "\n".join(
        f"{appointment.occurrence_number}. {format_appointment(appointment)}"
        for appointment in ordered_appointments
    )
    body = (
        f"Hello {first_appointment.user_name},\n\n"
        "Your recurring appointments have been successfully booked.\n\n"
        f"Service: {series.service.name}\n"
        f"Provider: {series.provider.name}\n"
        f"Schedule: {recurrence_rule}\n"
        f"Appointments: {len(ordered_appointments)}\n"
        f"Timezone: {series.timezone}\n"
        f"First appointment: {format_appointment(first_appointment)}\n"
        f"Last appointment: {format_appointment(last_appointment)}\n\n"
        "Appointment schedule:\n"
        f"{schedule}\n\n"
        "Thank you."
    )
    return "Recurring appointments confirmed", body


def send_booking_confirmation(db: Session, appointment: Appointment) -> None:
    """Deliver configured confirmation channels after booking is committed."""
    channels = [("email", appointment.user_email)]
    if appointment.user_phone:
        channels.append(("sms", appointment.user_phone))
    for channel, recipient in channels:
        notification = Notification(
            appointment_id=appointment.id,
            notification_type=NotificationType.CONFIRMATION,
            recipient_email=recipient if channel == "email" else None,
            recipient_phone=recipient if channel == "sms" else None,
        )
        db.add(notification)
        db.commit()
        deliver_notification(db, notification, appointment)


def send_status_email(
    db: Session,
    appointment: Appointment,
    notification_type: NotificationType,
    subject: str,
    body: str,
) -> None:
    try:
        notification = Notification(
            appointment_id=appointment.id,
            notification_type=notification_type,
            recipient_email=appointment.user_email,
        )
        db.add(notification)
        db.commit()
        _send_email(appointment, subject, body)
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to send %s notification for appointment %s",
            notification_type,
            appointment.id,
        )
    else:
        _record_result(db, notification, delivered=True)


def send_confirmation_status_email(db: Session, appointment: Appointment) -> None:
    send_status_email(
        db,
        appointment,
        NotificationType.CONFIRMATION,
        "Appointment confirmed",
        (
            f"Hello {appointment.user_name},\n\n"
            "Your appointment is confirmed.\n"
            f"Start: {appointment.appointment_start.isoformat()}\n"
            f"End: {appointment.appointment_end.isoformat()}"
        ),
    )


def send_cancellation_email(db: Session, appointment: Appointment) -> None:
    send_status_email(
        db,
        appointment,
        NotificationType.CANCELLATION,
        "Appointment cancelled",
        (
            f"Hello {appointment.user_name},\n\n"
            "Your appointment has been cancelled.\n"
            f"Scheduled start: {appointment.appointment_start.isoformat()}"
        ),
    )


def send_reschedule_email(db: Session, appointment: Appointment) -> None:
    send_status_email(
        db,
        appointment,
        NotificationType.RESCHEDULE,
        "Appointment rescheduled",
        (
            f"Hello {appointment.user_name},\n\n"
            "Your appointment has been rescheduled.\n"
            f"New start: {appointment.appointment_start.isoformat()}\n"
            f"New end: {appointment.appointment_end.isoformat()}"
        ),
    )
