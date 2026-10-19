from datetime import UTC, datetime, time, timedelta
from email.parser import BytesParser
from email.policy import default
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from celery.exceptions import Retry
from fastapi import BackgroundTasks
from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.appointment_series import AppointmentSeriesFrequency
from app.models.availability import ProviderAvailability
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.service import Service, ServiceStatus
from app.schemas.appointment import AppointmentCreate
from app.schemas.auth import CustomerRegister
from app.services.auth_service import register_user
from app.services.booking import create_appointment
from app.services.notifications import (
    _appointment_email,
    build_branded_email,
    build_series_confirmation_email,
    send_booking_confirmation,
    send_email,
)
from app.tasks.notification_tasks import (
    schedule_appointment_notifications,
    send_confirmation_notification,
    send_email_reminder,
    send_feedback_request,
    send_sms_reminder,
)


def _future_sunday_at_10() -> datetime:
    now = datetime.now(UTC)
    days_until_sunday = (6 - now.weekday()) % 7 or 7
    return datetime.combine(
        now.date() + timedelta(days=days_until_sunday),
        time(10),
        tzinfo=UTC,
    )


@pytest.fixture
def notification_records():
    db = SessionLocal()

    provider = Provider(
        name=f"Notification Provider {uuid4()}",
        type=ProviderType.PERSON,
        email=f"notification-{uuid4()}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )

    service = Service(
        name=f"Notification Service {uuid4()}",
        duration_minutes=30,
        category="Testing",
        capacity=1,
        buffer_time_minutes=0,
        status=ServiceStatus.ACTIVE,
    )

    db.add_all([provider, service])
    db.flush()

    db.add(
        ProviderService(
            provider_id=provider.id,
            service_id=service.id,
            is_active=True,
        )
    )

    db.add(
        ProviderAvailability(
            provider_id=provider.id,
            day_of_week=6,
            start_time=time(0, 0),
            end_time=time(23, 59, 59),
            is_working_day=True,
        )
    )

    db.commit()

    record_ids = provider.id, service.id
    db.close()

    try:
        yield record_ids
    finally:
        cleanup = SessionLocal()

        cleanup.execute(
            delete(Notification).where(
                Notification.appointment_id.in_(
                    select(Appointment.id).where(
                        Appointment.provider_id == record_ids[0]
                    )
                )
            )
        )
        cleanup.execute(
            delete(Appointment).where(Appointment.provider_id == record_ids[0])
        )
        cleanup.execute(
            delete(ProviderAvailability).where(
                ProviderAvailability.provider_id == record_ids[0]
            )
        )
        cleanup.execute(
            delete(ProviderService).where(ProviderService.provider_id == record_ids[0])
        )
        cleanup.execute(delete(Provider).where(Provider.id == record_ids[0]))
        cleanup.execute(delete(Service).where(Service.id == record_ids[1]))

        cleanup.commit()
        cleanup.close()


def test_schedule_appointment_notifications():
    appointment = type(
        "AppointmentStub",
        (),
        {
            "id": uuid4(),
            "appointment_start": datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
            "appointment_end": datetime(2026, 9, 20, 12, 30, tzinfo=UTC),
        },
    )()

    with patch("app.tasks.notification_tasks._schedule") as mock_schedule:
        schedule_appointment_notifications(appointment)

    assert mock_schedule.call_count == 3

    calls = mock_schedule.call_args_list

    assert calls[0].args[0].name == "appointments.send_email_reminder"
    assert calls[0].args[1] is appointment
    assert calls[0].args[2] == appointment.appointment_start - timedelta(hours=24)

    assert calls[1].args[0].name == "appointments.send_sms_reminder"
    assert calls[1].args[1] is appointment
    assert calls[1].args[2] == appointment.appointment_start - timedelta(hours=1)


def test_booking_confirmation_creates_sent_notification(notification_records):
    provider_id, service_id = notification_records

    db = SessionLocal()

    appointment = create_appointment(
        db,
        AppointmentCreate(
            service_id=service_id,
            provider_id=provider_id,
            user_name="Confirmation Test",
            user_email="confirmation@example.com",
            appointment_start=_future_sunday_at_10(),
        ),
    )

    with patch("app.services.notifications._send_email") as mock_send_email:
        send_booking_confirmation(db, appointment)

    notification = db.scalar(
        select(Notification)
        .where(
            Notification.appointment_id == appointment.id,
            Notification.notification_type == NotificationType.CONFIRMATION,
        )
        .order_by(Notification.created_at.desc())
    )

    db.close()

    assert notification is not None
    assert notification.status == NotificationStatus.SENT
    mock_send_email.assert_called_once()


def test_confirmation_task_is_idempotent_on_redelivery(notification_records):
    provider_id, service_id = notification_records
    with SessionLocal() as db:
        appointment = create_appointment(
            db,
            AppointmentCreate(
                service_id=service_id,
                provider_id=provider_id,
                user_name="Repeated Confirmation Test",
                user_email=f"repeated-confirmation-{uuid4()}@example.com",
                appointment_start=_future_sunday_at_10(),
            ),
        )
        appointment_id = str(appointment.id)

    with patch("app.services.notifications._send_email") as mock_send_email:
        send_confirmation_notification.run(appointment_id)
        send_confirmation_notification.run(appointment_id)

    with SessionLocal() as db:
        notifications = db.scalars(
            select(Notification).where(
                Notification.appointment_id == appointment.id,
                Notification.notification_type == NotificationType.CONFIRMATION,
                Notification.recipient_email == appointment.user_email,
            )
        ).all()

    assert len(notifications) == 1
    assert notifications[0].status == NotificationStatus.SENT
    mock_send_email.assert_called_once()


def test_one_time_booking_still_queues_confirmation_and_reminders(
    notification_records, monkeypatch
):
    provider_id, service_id = notification_records
    confirmation_appointments = []
    scheduled_appointments = []
    monkeypatch.setattr(
        "app.services.booking.enqueue_confirmation_notification",
        lambda appointment: confirmation_appointments.append(appointment.id),
    )
    monkeypatch.setattr(
        "app.services.booking.schedule_appointment_notifications",
        lambda appointment: scheduled_appointments.append(appointment.id),
    )
    with SessionLocal() as db:
        appointment = create_appointment(
            db,
            AppointmentCreate(
                service_id=service_id,
                provider_id=provider_id,
                user_name="One-time Notification Test",
                user_email="one-time-notification@example.com",
                appointment_start=_future_sunday_at_10(),
            ),
        )

    assert confirmation_appointments == [appointment.id]
    assert scheduled_appointments == [appointment.id]


def test_cancellation_notification_is_sent(notification_records):
    provider_id, service_id = notification_records

    db = SessionLocal()

    appointment = create_appointment(
        db,
        AppointmentCreate(
            service_id=service_id,
            provider_id=provider_id,
            user_name="Cancellation Notification Test",
            user_email="cancellation-notification@example.com",
            appointment_start=_future_sunday_at_10(),
        ),
    )

    with patch("app.services.notifications._send_email") as mock_send_email:
        from app.services.notifications import send_cancellation_email

        send_cancellation_email(db, appointment)

    notification = db.scalar(
        select(Notification)
        .where(
            Notification.appointment_id == appointment.id,
            Notification.notification_type == NotificationType.CANCELLATION,
        )
        .order_by(Notification.created_at.desc())
    )

    db.close()

    assert notification is not None
    assert notification.status == NotificationStatus.SENT
    mock_send_email.assert_called_once()


def test_email_reminder_has_retry_configuration():
    assert Exception in send_email_reminder.autoretry_for
    assert send_email_reminder.retry_backoff is True
    assert send_email_reminder.retry_kwargs["max_retries"] == 3


class _NotificationTaskSession:
    def __init__(self, appointment, notification=None):
        self.appointment = appointment
        self.notification = notification
        self.scalar_calls = 0
        self.commit_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def get(self, _model, _appointment_id):
        return self.appointment

    def scalar(self, _query):
        self.scalar_calls += 1
        return self.notification

    def add(self, notification):
        self.notification = notification

    def commit(self):
        self.commit_calls += 1

    def flush(self):
        pass


def _notification_task_records(
    notification_type=NotificationType.REMINDER,
    status=NotificationStatus.PENDING,
    *,
    phone=None,
):
    appointment = _email_appointment(
        id=uuid4(),
        status=AppointmentStatus.CONFIRMED,
        user_email="task-test@example.com",
        user_phone=phone,
    )
    notification = SimpleNamespace(
        id=uuid4(),
        status=status,
        retry_count=0,
        sent_at=None,
        notification_type=notification_type,
        recipient_email=None if phone else appointment.user_email,
        recipient_phone=phone,
    )
    return appointment, notification


def _use_notification_task_session(monkeypatch, appointment, notification=None):
    sessions = []

    def session_factory():
        session = _NotificationTaskSession(appointment, notification)
        sessions.append(session)
        return session

    monkeypatch.setattr("app.tasks.notification_tasks.SessionLocal", session_factory)
    return sessions


def test_email_reminder_success_uses_persisted_sent_status(monkeypatch):
    appointment, notification = _notification_task_records()
    sessions = _use_notification_task_session(monkeypatch, appointment, notification)
    send_email_mock = MagicMock()
    monkeypatch.setattr("app.services.notifications._send_email", send_email_mock)

    send_email_reminder.run(str(appointment.id))

    assert notification.status == NotificationStatus.SENT
    assert notification.retry_count == 1
    assert notification.sent_at is not None
    send_email_mock.assert_called_once()
    assert len(sessions) == 2


def test_email_reminder_delivery_failure_preserves_failed_status_and_raises(
    monkeypatch,
):
    appointment, notification = _notification_task_records()
    _use_notification_task_session(monkeypatch, appointment, notification)
    send_email_mock = MagicMock(side_effect=OSError("SMTP unavailable"))
    monkeypatch.setattr("app.services.notifications._send_email", send_email_mock)

    with pytest.raises(RuntimeError, match="Email reminder delivery failed"):
        send_email_reminder.run(str(appointment.id))

    assert notification.status == NotificationStatus.FAILED
    assert notification.retry_count == 1
    assert notification.sent_at is None
    send_email_mock.assert_called_once()


def test_feedback_request_success_uses_persisted_sent_status(monkeypatch):
    appointment, notification = _notification_task_records(
        NotificationType.FEEDBACK_REQUEST
    )
    _use_notification_task_session(monkeypatch, appointment, notification)
    send_email_mock = MagicMock()
    monkeypatch.setattr("app.services.notifications._send_email", send_email_mock)

    send_feedback_request.run(str(appointment.id))

    assert notification.status == NotificationStatus.SENT
    assert notification.retry_count == 1
    assert notification.sent_at is not None
    send_email_mock.assert_called_once()


def test_sms_reminder_without_twilio_configuration_fails_safely(
    monkeypatch, caplog
):
    appointment, notification = _notification_task_records(phone="+15555550123")
    _use_notification_task_session(monkeypatch, appointment, notification)
    monkeypatch.setattr("app.services.notifications.settings.twilio_account_sid", None)
    monkeypatch.setattr("app.services.notifications.settings.twilio_auth_token", None)
    monkeypatch.setattr("app.services.notifications.settings.twilio_from_phone", None)
    urlopen_mock = MagicMock()
    monkeypatch.setattr("app.services.notifications.urlopen", urlopen_mock)
    retry_mock = MagicMock()
    monkeypatch.setattr(send_sms_reminder, "retry", retry_mock)

    with caplog.at_level("ERROR", logger="app.services.notifications"):
        send_sms_reminder.run(str(appointment.id))

    assert notification.status == NotificationStatus.FAILED
    assert notification.retry_count == 1
    assert notification.sent_at is None
    assert "SMS is not configured" in caplog.text
    urlopen_mock.assert_not_called()
    retry_mock.assert_not_called()


def test_transient_sms_delivery_failure_uses_celery_retry(monkeypatch):
    appointment, notification = _notification_task_records(phone="+15555550123")
    _use_notification_task_session(monkeypatch, appointment, notification)
    monkeypatch.setattr(
        "app.services.notifications.settings.twilio_account_sid", "ACtest"
    )
    monkeypatch.setattr(
        "app.services.notifications.settings.twilio_auth_token", "test-token"
    )
    monkeypatch.setattr(
        "app.services.notifications.settings.twilio_from_phone", "+15555550124"
    )
    urlopen_mock = MagicMock(side_effect=OSError("Twilio unavailable"))
    monkeypatch.setattr("app.services.notifications.urlopen", urlopen_mock)
    retry_mock = MagicMock(return_value=Retry())
    monkeypatch.setattr(send_sms_reminder, "retry", retry_mock)

    with pytest.raises(Retry):
        send_sms_reminder.run(str(appointment.id))

    assert notification.status == NotificationStatus.FAILED
    assert notification.retry_count == 1
    urlopen_mock.assert_called_once()
    retry_mock.assert_called_once()
    assert isinstance(retry_mock.call_args.kwargs["exc"], RuntimeError)
    assert Exception in send_sms_reminder.autoretry_for
    assert send_sms_reminder.retry_backoff is True
    assert send_sms_reminder.retry_kwargs["max_retries"] == 3


@pytest.mark.parametrize(
    ("task", "notification_type", "phone"),
    [
        (send_email_reminder, NotificationType.REMINDER, None),
        (send_sms_reminder, NotificationType.REMINDER, "+15555550123"),
        (send_feedback_request, NotificationType.FEEDBACK_REQUEST, None),
    ],
)
def test_already_sent_notification_is_not_delivered_again(
    monkeypatch, task, notification_type, phone
):
    appointment, notification = _notification_task_records(
        notification_type,
        NotificationStatus.SENT,
        phone=phone,
    )
    notification.sent_at = datetime.now(UTC)
    _use_notification_task_session(monkeypatch, appointment, notification)
    send_email_mock = MagicMock()
    urlopen_mock = MagicMock()
    monkeypatch.setattr("app.services.notifications._send_email", send_email_mock)
    monkeypatch.setattr("app.services.notifications.urlopen", urlopen_mock)

    task.run(str(appointment.id))

    assert notification.status == NotificationStatus.SENT
    assert notification.retry_count == 0
    send_email_mock.assert_not_called()
    urlopen_mock.assert_not_called()


@pytest.mark.parametrize(
    ("task", "phone"),
    [
        (send_email_reminder, None),
        (send_sms_reminder, "+15555550123"),
        (send_feedback_request, None),
    ],
)
def test_cancelled_appointment_notification_is_skipped_without_retry(
    monkeypatch, task, phone
):
    appointment, _notification = _notification_task_records(phone=phone)
    appointment.status = AppointmentStatus.CANCELLED
    sessions = _use_notification_task_session(monkeypatch, appointment)
    send_email_mock = MagicMock()
    urlopen_mock = MagicMock()
    monkeypatch.setattr("app.services.notifications._send_email", send_email_mock)
    monkeypatch.setattr("app.services.notifications.urlopen", urlopen_mock)

    task.run(str(appointment.id))

    assert all(session.scalar_calls == 0 for session in sessions)
    send_email_mock.assert_not_called()
    urlopen_mock.assert_not_called()


def _email_appointment(**overrides):
    appointment = {
        "user_name": '<Alex & "Co">',
        "appointment_start": datetime(2026, 10, 19, 4, 30, tzinfo=UTC),
        "appointment_end": datetime(2026, 10, 19, 5, 0, tzinfo=UTC),
        "duration_minutes": 30,
        "provider": SimpleNamespace(name="<Dr. Example>", timezone="Asia/Kolkata"),
        "service": SimpleNamespace(name="General Consultation"),
    }
    appointment.update(overrides)
    return SimpleNamespace(**appointment)


@pytest.mark.parametrize(
    ("notification_type", "expected_subject", "expected_phrase"),
    [
        (
            NotificationType.CONFIRMATION,
            "Your appointment is confirmed",
            "successfully booked and confirmed",
        ),
        (
            NotificationType.REMINDER,
            "Reminder: your upcoming appointment",
            "reminder that your appointment is coming up",
        ),
        (
            NotificationType.CANCELLATION,
            "Your appointment has been cancelled",
            "cancelled as requested",
        ),
        (
            NotificationType.RESCHEDULE,
            "Your appointment schedule has changed",
            "rescheduled",
        ),
        (
            NotificationType.FEEDBACK_REQUEST,
            "Thank you for your visit — share your feedback",
            "Thank you for attending your appointment",
        ),
    ],
)
def test_event_emails_include_local_appointment_details(
    notification_type, expected_subject, expected_phrase
):
    subject, body, html_body, _ = _appointment_email(
        notification_type, _email_appointment()
    )

    assert subject == expected_subject
    assert expected_phrase in body
    assert "Monday, 19 October 2026" in body
    assert "10:00 AM – 10:30 AM IST" in body
    assert "30 minutes" in body
    assert "General Consultation" in body
    assert "<Dr. Example>" in body
    assert "Appointment Booking System" in body
    assert "<h1" in html_body
    assert "General Consultation" in html_body
    assert "&lt;Dr. Example&gt;" in html_body
    assert "2026-10-19T04:30:00" not in body


def test_reschedule_email_includes_old_and_new_schedules():
    previous_start = datetime(2026, 10, 18, 4, 30, tzinfo=UTC)
    previous_end = datetime(2026, 10, 18, 5, 0, tzinfo=UTC)

    _, body, _, _ = _appointment_email(
        NotificationType.RESCHEDULE,
        _email_appointment(),
        previous_start=previous_start,
        previous_end=previous_end,
    )

    assert "Previous appointment Date: Sunday, 18 October 2026" in body
    assert "New appointment Date: Monday, 19 October 2026" in body
    assert "follow the updated schedule" in body


def test_cancellation_email_does_not_claim_a_refund():
    _, body, _, _ = _appointment_email(
        NotificationType.CANCELLATION, _email_appointment()
    )

    assert "does not confirm a refund" in body
    assert "refund has been processed" not in body.lower()


def test_missing_provider_details_are_omitted_from_email():
    appointment = _email_appointment(provider=None, service=None)
    _, body, html_body, _ = _appointment_email(NotificationType.REMINDER, appointment)

    assert "Provider:" not in body
    assert "Service:" not in body
    assert "Location:" not in body
    assert "Appointment date: Monday, 19 October 2026" in body
    assert "General Consultation" not in html_body


def test_dynamic_email_content_is_html_escaped():
    body, html_body = build_branded_email(
        "Welcome <customer>",
        '<img src=x onerror="alert(1)">',
        "Your account is ready for <booking>.",
        [("Service", "<script>danger</script>")],
    )

    assert "<img" not in html_body
    assert "<script>" not in html_body
    assert "&lt;img" in html_body
    assert "&lt;script&gt;" in html_body
    assert "<customer>" not in body


def test_series_confirmation_contains_recurrence_and_each_local_schedule():
    first = _email_appointment(occurrence_number=1)
    second = _email_appointment(
        occurrence_number=2,
        appointment_start=datetime(2026, 10, 26, 4, 30, tzinfo=UTC),
        appointment_end=datetime(2026, 10, 26, 5, 0, tzinfo=UTC),
    )
    series = SimpleNamespace(
        frequency=AppointmentSeriesFrequency.WEEKLY,
        interval=2,
        service=SimpleNamespace(name="General Consultation"),
        provider=SimpleNamespace(name="Dr. Example"),
        timezone="Asia/Kolkata",
    )

    subject, body, html_body = build_series_confirmation_email(series, [first, second])

    assert subject == "Your recurring appointments are confirmed"
    assert "Recurrence: Every two weeks" in body
    assert "Number of appointments: 2" in body
    assert "1. Monday, 19 October 2026 — 10:00 AM – 10:30 AM IST (30 minutes)" in body
    assert "2. Monday, 26 October 2026 — 10:00 AM – 10:30 AM IST (30 minutes)" in body
    assert "<table" in html_body


def test_send_email_provides_plain_text_and_html_alternatives(monkeypatch):
    monkeypatch.setattr("app.services.notifications.settings.smtp_host", "smtp.example")
    monkeypatch.setattr(
        "app.services.notifications.settings.smtp_from", "from@example.com"
    )
    smtp_client = MagicMock()
    smtp_client.__enter__.return_value = smtp_client
    monkeypatch.setattr(
        "app.services.notifications.smtplib.SMTP", lambda *_args: smtp_client
    )

    send_email(
        "customer@example.com",
        "Appointment confirmed",
        "Plain-text appointment details",
        html_body="<html><body>HTML appointment details</body></html>",
    )

    message = smtp_client.send_message.call_args.args[0]
    parsed = BytesParser(policy=default).parsebytes(message.as_bytes())
    assert parsed.is_multipart()
    assert parsed.get_body(preferencelist=("plain",)).get_content().strip() == (
        "Plain-text appointment details"
    )
    assert (
        "HTML appointment details"
        in parsed.get_body(preferencelist=("html",)).get_content()
    )


def test_registration_email_is_welcome_only_and_personalized(monkeypatch):
    class InMemorySession:
        added = None

        def scalar(self, _query):
            return None

        def add(self, instance):
            self.added = instance

        def commit(self):
            pass

        def refresh(self, _instance):
            pass

    monkeypatch.setattr(
        "app.services.auth_service.hash_password", lambda _password: "hash"
    )
    background_tasks = BackgroundTasks()
    user = register_user(
        InMemorySession(),
        CustomerRegister(
            name="<Alex>",
            email="alex@example.com",
            password="a-long-test-password",
        ),
        background_tasks,
    )

    task = background_tasks.tasks[0]
    assert user.name == "<Alex>"
    assert task.args[1] == "Welcome to Appointment Booking System"
    assert "Hello <Alex>," in task.args[2]
    assert "account has been created successfully" in task.args[2]
    assert "appointment date" not in task.args[2].lower()
    assert "&lt;Alex&gt;" in task.kwargs["html_body"]
