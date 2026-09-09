import logging
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.notification import Notification, NotificationStatus, NotificationType

logger = logging.getLogger(__name__)


def _message(appointment: Appointment) -> str:
    return (
        f"Hello {appointment.user_name},\n\n"
        "Your appointment has been confirmed.\n"
        f"Start: {appointment.appointment_start.isoformat()}\n"
        f"End: {appointment.appointment_end.isoformat()}\n\n"
        "Thank you."
    )


def _send_email(appointment: Appointment) -> None:
    if not settings.smtp_host or not settings.smtp_from:
        raise RuntimeError("SMTP is not configured")

    message = EmailMessage()
    message["Subject"] = "Appointment confirmation"
    message["From"] = settings.smtp_from
    message["To"] = appointment.user_email
    message.set_content(_message(appointment))
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as client:
        if settings.smtp_starttls:
            client.starttls()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password or "")
        client.send_message(message)


def _send_sms(appointment: Appointment) -> None:
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
            "Body": "Your appointment has been confirmed.",
        }
    ).encode()
    request = Request(
        "https://api.twilio.com/2010-04-01/Accounts/"
        f"{settings.twilio_account_sid}/Messages.json",
        data=body,
        method="POST",
    )
    import base64

    credentials = f"{settings.twilio_account_sid}:{settings.twilio_auth_token}"
    request.add_header(
        "Authorization", "Basic " + base64.b64encode(credentials.encode()).decode()
    )
    with urlopen(request, timeout=10):
        pass


def _record_result(
    db: Session, notification: Notification, delivered: bool
) -> None:
    notification.status = (
        NotificationStatus.SENT if delivered else NotificationStatus.FAILED
    )
    notification.retry_count += 1
    if delivered:
        notification.sent_at = datetime.now(UTC)
    db.commit()


def send_booking_confirmation(db: Session, appointment: Appointment) -> None:
    """Deliver configured confirmation channels after booking is committed."""
    channels = [("email", appointment.user_email, _send_email)]
    if appointment.user_phone:
        channels.append(("sms", appointment.user_phone, _send_sms))

    for channel, recipient, sender in channels:
        notification = Notification(
            appointment_id=appointment.id,
            notification_type=NotificationType.CONFIRMATION,
            recipient_email=recipient if channel == "email" else None,
            recipient_phone=recipient if channel == "sms" else None,
            status=NotificationStatus.PENDING,
        )
        db.add(notification)
        db.commit()
        try:
            sender(appointment)
        except Exception:
            logger.exception("Failed to send appointment confirmation via %s", channel)
            _record_result(db, notification, delivered=False)
        else:
            _record_result(db, notification, delivered=True)