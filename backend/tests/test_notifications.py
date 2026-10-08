from datetime import UTC, datetime, time, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.models.appointment import Appointment
from app.models.availability import ProviderAvailability
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.service import Service, ServiceStatus
from app.schemas.appointment import AppointmentCreate
from app.services.booking import create_appointment
from app.services.notifications import send_booking_confirmation
from app.tasks.notification_tasks import (
    schedule_appointment_notifications,
    send_confirmation_notification,
    send_email_reminder,
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
