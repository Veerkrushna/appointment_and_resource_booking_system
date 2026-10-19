import base64
import html
import logging
import smtplib
from collections.abc import Iterable
from datetime import UTC, datetime
from email.message import EmailMessage
from enum import StrEnum
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timezones import to_local
from app.models.appointment import Appointment
from app.models.appointment_series import AppointmentSeries
from app.models.notification import Notification, NotificationStatus, NotificationType

logger = logging.getLogger(__name__)

BRAND_NAME = "Appointment Booking System"


class NotificationConfigurationError(RuntimeError):
    pass


class NotificationDeliveryResult(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    CONFIGURATION_ERROR = "configuration_error"


def build_branded_email(
    title: str,
    recipient_name: str | None,
    opening: str,
    details: Iterable[tuple[str, str]] = (),
    closing: str = "Thank you for choosing us.",
    details_heading: str = "Details",
) -> tuple[str, str]:
    greeting = (
        f"Hello {recipient_name.strip()},"
        if recipient_name and recipient_name.strip()
        else "Hello,"
    )
    detail_rows = list(details)
    text_parts = [greeting, "", opening]
    if detail_rows:
        text_parts.extend(["", f"{details_heading}:"])
        text_parts.extend(f"{label}: {value}" for label, value in detail_rows)
    text_parts.extend(["", closing, "", BRAND_NAME])
    text_body = "\n".join(text_parts)

    escaped_title = html.escape(title)
    escaped_greeting = html.escape(greeting)
    escaped_opening = html.escape(opening)
    escaped_closing = html.escape(closing)
    detail_html = ""
    if detail_rows:
        detail_html = (
            f'<h2 style="margin:22px 0 8px;color:#333333;font-size:16px;">'
            f"{html.escape(details_heading)}</h2>"
        )
        rows = "".join(
            "<tr>"
            '<td style="padding:9px 12px;border-bottom:1px solid #eeeeee;'
            'font-weight:600;color:#333333;vertical-align:top;">'
            f"{html.escape(label)}</td>"
            '<td style="padding:9px 12px;border-bottom:1px solid #eeeeee;'
            f'color:#333333;">{html.escape(value).replace(chr(10), "<br>")}</td></tr>'
            for label, value in detail_rows
        )
        detail_html += (
            '<table role="presentation" cellpadding="0" cellspacing="0" '
            'width="100%" style="border-collapse:collapse;margin:22px 0;'
            'background-color:#fff8f2;border:1px solid #f1e2d6;">'
            f"{rows}</table>"
        )
    html_body = (
        '<!doctype html><html><body style="margin:0;padding:0;'
        "background-color:#f5f5f5;font-family:Arial,Helvetica,sans-serif;"
        'color:#222222;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background-color:#f5f5f5;padding:24px 12px;"><tr><td align="center">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="width:100%;max-width:600px;background-color:#ffffff;'
        'border-collapse:collapse;">'
        '<tr><td style="padding:22px 28px;background-color:#f47b20;color:#ffffff;'
        'font-size:18px;font-weight:bold;">'
        f"{html.escape(BRAND_NAME)}</td></tr>"
        '<tr><td style="padding:28px;font-size:15px;line-height:1.6;">'
        f'<h1 style="margin:0 0 20px;color:#222222;font-size:23px;'
        f'line-height:1.3;">{escaped_title}</h1>'
        f'<p style="margin:0 0 14px;">{escaped_greeting}</p>'
        f'<p style="margin:0 0 14px;">{escaped_opening}</p>'
        f"{detail_html}"
        f'<p style="margin:22px 0 0;">{escaped_closing}</p>'
        '</td></tr><tr><td style="padding:18px 28px;background-color:#222222;'
        'color:#ffffff;font-size:12px;line-height:1.5;">'
        f"{html.escape(BRAND_NAME)}"
        "</td></tr></table></td></tr></table></body></html>"
    )
    return text_body, html_body


def send_email(
    to_email: str,
    subject: str,
    body: str,
    *,
    html_body: str | None = None,
) -> None:
    if not settings.smtp_host or not settings.smtp_from:
        raise RuntimeError("SMTP is not configured")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = to_email
    message.set_content(body)
    if html_body is None:
        _, html_body = build_branded_email(
            subject,
            None,
            body,
            closing="",
        )
    message.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as client:
        if settings.smtp_starttls:
            client.starttls()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password or "")
        client.send_message(message)


def _send_email(
    appointment: Appointment,
    subject: str,
    body: str,
    *,
    html_body: str | None = None,
) -> None:
    send_email(appointment.user_email, subject, body, html_body=html_body)


def _send_sms(appointment: Appointment, body_text: str) -> None:
    if not appointment.user_phone:
        return
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise NotificationConfigurationError("SMS is not configured")
    if not settings.twilio_from_phone:
        raise NotificationConfigurationError("Twilio sender phone is not configured")
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


def _appointment_details(
    appointment: Appointment,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    prefix: str = "",
) -> list[tuple[str, str]]:
    provider = getattr(appointment, "provider", None)
    timezone_name = getattr(provider, "timezone", None) or "UTC"
    start = start or appointment.appointment_start
    end = end or appointment.appointment_end
    local_start = to_local(start, timezone_name)
    local_end = to_local(end, timezone_name)
    date_label = local_start.strftime("%A, %d %B %Y")
    start_zone = local_start.tzname() or timezone_name
    end_zone = local_end.tzname() or timezone_name
    timezone_label = (
        start_zone if start_zone == end_zone else f"{start_zone}–{end_zone}"
    )
    time_label = (
        f"{local_start.strftime('%I:%M %p').lstrip('0')} – "
        f"{local_end.strftime('%I:%M %p').lstrip('0')} {timezone_label}"
    )
    details = [
        (f"{prefix}Date" if prefix else "Appointment date", date_label),
        (f"{prefix}Time" if prefix else "Time", time_label),
    ]
    if local_start.date() != local_end.date():
        details.append(
            (
                f"{prefix}End date" if prefix else "End date",
                local_end.strftime("%A, %d %B %Y"),
            )
        )
    duration = getattr(appointment, "duration_minutes", None)
    if duration is None:
        duration = int(
            (local_end.astimezone(UTC) - local_start.astimezone(UTC)).total_seconds()
            // 60
        )
    details.append(
        (f"{prefix}Duration" if prefix else "Duration", f"{duration} minutes")
    )
    service_name = getattr(getattr(appointment, "service", None), "name", None)
    if service_name:
        details.append((f"{prefix}Service" if prefix else "Service", service_name))
    provider_name = getattr(provider, "name", None)
    if provider_name:
        details.append((f"{prefix}Provider" if prefix else "Provider", provider_name))
    return details


def _appointment_email(
    notification_type: NotificationType,
    appointment: Appointment,
    *,
    previous_start: datetime | None = None,
    previous_end: datetime | None = None,
) -> tuple[str, str, str, str]:
    details = _appointment_details(appointment)
    name = appointment.user_name
    if notification_type == NotificationType.CONFIRMATION:
        subject = "Your appointment is confirmed"
        opening = "Your appointment has been successfully booked and confirmed."
        closing = (
            "Please arrive on time. You can manage your booking by signing in to "
            "the application."
        )
        sms_body = "Your appointment is confirmed."
    elif notification_type == NotificationType.REMINDER:
        subject = "Reminder: your upcoming appointment"
        opening = "This is a reminder that your appointment is coming up."
        closing = "We look forward to seeing you."
        sms_body = "Reminder: your appointment is coming up soon."
    elif notification_type == NotificationType.CANCELLATION:
        subject = "Your appointment has been cancelled"
        opening = "Your appointment has been cancelled as requested."
        closing = (
            "This message confirms the cancellation only; it does not confirm a "
            "refund. Please sign in to the application if you need to make another "
            "booking or have questions about your payment."
        )
        sms_body = "Your appointment has been cancelled."
    elif notification_type == NotificationType.RESCHEDULE:
        subject = "Your appointment schedule has changed"
        opening = (
            "Your appointment has been rescheduled. Please follow the updated "
            "schedule below; the previous time is no longer current."
        )
        if previous_start is not None and previous_end is not None:
            details = _appointment_details(
                appointment,
                start=previous_start,
                end=previous_end,
                prefix="Previous appointment ",
            ) + _appointment_details(
                appointment,
                prefix="New appointment ",
            )
        else:
            details.insert(0, ("Updated schedule", ""))
        closing = "Please use the updated date and time for your appointment."
        sms_body = (
            "Your appointment has been rescheduled. Please check the updated schedule."
        )
    else:
        subject = "Thank you for your visit — share your feedback"
        opening = (
            "Thank you for attending your appointment. If you are eligible, we "
            "invite you to sign in to the application and share a review."
        )
        closing = "Your feedback helps us improve."
        sms_body = "Thank you for attending. Please share your feedback when eligible."

    plain_body, html_body = build_branded_email(
        subject,
        name,
        opening,
        details,
        closing,
        details_heading="Appointment details",
    )
    return subject, plain_body, html_body, sms_body


def deliver_notification(
    db: Session,
    notification: Notification,
    appointment: Appointment,
    *,
    previous_start: datetime | None = None,
    previous_end: datetime | None = None,
) -> NotificationDeliveryResult:
    is_email = notification.recipient_email is not None
    try:
        if is_email:
            subject, body, html_body, _ = _appointment_email(
                notification.notification_type,
                appointment,
                previous_start=previous_start,
                previous_end=previous_end,
            )
            _send_email(appointment, subject, body, html_body=html_body)
        else:
            _send_sms(
                appointment,
                {
                    NotificationType.CONFIRMATION: "Your appointment is confirmed.",
                    NotificationType.REMINDER: "Reminder: your appointment is coming up soon.",
                    NotificationType.CANCELLATION: "Your appointment has been cancelled.",
                    NotificationType.RESCHEDULE: (
                        "Your appointment has been rescheduled. "
                        "Please check the updated schedule."
                    ),
                    NotificationType.FEEDBACK_REQUEST: (
                        "Thank you for attending. Please share your feedback when eligible."
                    ),
                }[notification.notification_type],
            )
    except Exception as exc:
        logger.exception("Failed to send notification %s", notification.id)
        _record_result(db, notification, delivered=False)
        if isinstance(exc, NotificationConfigurationError):
            return NotificationDeliveryResult.CONFIGURATION_ERROR
        return NotificationDeliveryResult.FAILED
    else:
        _record_result(db, notification, delivered=True)
        return NotificationDeliveryResult.SENT


def deliver_email_notification(
    db: Session,
    notification: Notification,
    recipient_email: str,
    subject: str,
    body: str,
    *,
    html_body: str | None = None,
    appointment: Appointment | None = None,
) -> bool:
    try:
        if appointment is not None:
            _send_email(appointment, subject, body, html_body=html_body)
        else:
            send_email(recipient_email, subject, body, html_body=html_body)
    except Exception:
        logger.exception("Failed to send notification %s", notification.id)
        _record_result(db, notification, delivered=False)
        return False

    _record_result(db, notification, delivered=True)
    return True


def build_series_confirmation_email(
    series: AppointmentSeries, appointments: list[Appointment]
) -> tuple[str, str, str]:
    ordered_appointments = sorted(
        appointments, key=lambda appointment: appointment.occurrence_number or 0
    )
    if series.frequency.value == "weekly":
        recurrence_rule = "Every two weeks" if series.interval == 2 else "Every week"
    else:
        recurrence_rule = "Every month"

    first_appointment = ordered_appointments[0]
    last_appointment = ordered_appointments[-1]

    def format_occurrence(appointment: Appointment) -> str:
        details = dict(_appointment_details(appointment))
        return (
            f"{appointment.occurrence_number}. {details['Appointment date']} — "
            f"{details['Time']} ({details['Duration']})"
        )

    schedule = "\n".join(
        format_occurrence(appointment) for appointment in ordered_appointments
    )
    first_schedule = format_occurrence(first_appointment).split(". ", 1)[1]
    last_schedule = format_occurrence(last_appointment).split(". ", 1)[1]
    details = [
        ("Service", series.service.name),
        ("Provider", series.provider.name),
        ("Recurrence", recurrence_rule),
        ("Number of appointments", str(len(ordered_appointments))),
        ("First appointment", first_schedule),
        ("Last appointment", last_schedule),
        ("Timezone", series.timezone),
        ("Full appointment schedule", schedule),
    ]
    subject = "Your recurring appointments are confirmed"
    body, html_body = build_branded_email(
        subject,
        first_appointment.user_name,
        "Your recurring appointments have been successfully booked.",
        details,
        "Please follow the schedule above. You can manage your bookings by signing "
        "in to the application.",
        details_heading="Recurring appointment details",
    )
    return subject, body, html_body


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
        if channel == "email":
            subject, body, html_body, _ = _appointment_email(
                NotificationType.CONFIRMATION, appointment
            )
            delivered = deliver_email_notification(
                db,
                notification,
                recipient,
                subject,
                body,
                html_body=html_body,
                appointment=appointment,
            )
            if not delivered:
                continue
        else:
            deliver_notification(db, notification, appointment)


def send_status_email(
    db: Session,
    appointment: Appointment,
    notification_type: NotificationType,
    subject: str,
    body: str,
    *,
    html_body: str | None = None,
) -> None:
    try:
        notification = Notification(
            appointment_id=appointment.id,
            notification_type=notification_type,
            recipient_email=appointment.user_email,
        )
        db.add(notification)
        db.commit()
        _send_email(appointment, subject, body, html_body=html_body)
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
    subject, body, html_body, _ = _appointment_email(
        NotificationType.CONFIRMATION, appointment
    )
    send_status_email(
        db,
        appointment,
        NotificationType.CONFIRMATION,
        subject,
        body,
        html_body=html_body,
    )


def send_cancellation_email(db: Session, appointment: Appointment) -> None:
    subject, body, html_body, _ = _appointment_email(
        NotificationType.CANCELLATION, appointment
    )
    send_status_email(
        db,
        appointment,
        NotificationType.CANCELLATION,
        subject,
        body,
        html_body=html_body,
    )


def send_reschedule_email(
    db: Session,
    appointment: Appointment,
    previous_start: datetime | None = None,
    previous_end: datetime | None = None,
) -> None:
    subject, body, html_body, _ = _appointment_email(
        NotificationType.RESCHEDULE,
        appointment,
        previous_start=previous_start,
        previous_end=previous_end,
    )
    send_status_email(
        db,
        appointment,
        NotificationType.RESCHEDULE,
        subject,
        body,
        html_body=html_body,
    )
