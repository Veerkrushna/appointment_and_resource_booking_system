from datetime import UTC, datetime, time, timedelta
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.appointment_cancellation import AppointmentCancellation
from app.models.appointment_series import (
    AppointmentSeries,
    AppointmentSeriesEndMode,
    AppointmentSeriesFrequency,
)
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.service import Service, ServiceStatus
from app.models.user import User, UserRole
from app.services.appointment_series import cancel_appointment_series
from app.services.booking import cancel_appointment
from app.tasks.notification_tasks import (
    schedule_appointment_notifications,
    send_email_reminder,
)


@pytest.fixture
def recurring_reminder_records():
    owner = User(
        name="Series Owner",
        email=f"series-owner-{uuid4()}@example.com",
        password_hash="not-used",
        role=UserRole.CUSTOMER,
    )
    provider = Provider(
        name=f"Reminder Provider {uuid4()}",
        type=ProviderType.PERSON,
        email=f"reminder-provider-{uuid4()}@example.com",
        timezone="Asia/Kolkata",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    service = Service(
        name=f"Reminder Service {uuid4()}",
        duration_minutes=30,
        category="Testing",
        capacity=1,
        buffer_time_minutes=0,
        status=ServiceStatus.ACTIVE,
    )

    with SessionLocal() as db:
        db.add_all([owner, provider, service])
        db.flush()

        first_local_date = datetime.now(ZoneInfo("Asia/Kolkata")).date() + timedelta(
            days=14
        )
        series = AppointmentSeries(
            customer_id=owner.id,
            provider_id=provider.id,
            service_id=service.id,
            frequency=AppointmentSeriesFrequency.WEEKLY,
            interval=1,
            start_date=first_local_date,
            local_start_time=time(10),
            timezone=provider.timezone,
            end_mode=AppointmentSeriesEndMode.COUNT,
            occurrence_count=3,
        )
        db.add(series)
        db.flush()

        appointments = []
        for occurrence_number in range(1, 4):
            local_start = datetime.combine(
                first_local_date + timedelta(weeks=occurrence_number - 1),
                time(10),
                tzinfo=ZoneInfo(provider.timezone),
            )
            start_utc = local_start.astimezone(UTC)
            appointments.append(
                Appointment(
                    service_id=service.id,
                    provider_id=provider.id,
                    customer_id=owner.id,
                    series_id=series.id,
                    occurrence_number=occurrence_number,
                    user_name="Recipient B",
                    user_email=f"recipient-b-{uuid4()}@example.com",
                    appointment_start=start_utc,
                    appointment_end=start_utc + timedelta(minutes=30),
                    duration_minutes=30,
                    buffer_time_minutes=0,
                    status=AppointmentStatus.CONFIRMED,
                )
            )
        db.add_all(appointments)
        db.commit()
        db.refresh(series)
        appointment_ids = [appointment.id for appointment in appointments]
        records = {
            "owner_id": owner.id,
            "owner_email": owner.email,
            "provider_id": provider.id,
            "service_id": service.id,
            "series_id": series.id,
            "appointment_ids": appointment_ids,
        }

    try:
        yield records
    finally:
        with SessionLocal() as db:
            db.execute(
                delete(Notification).where(
                    Notification.appointment_id.in_(
                        select(Appointment.id).where(
                            Appointment.provider_id == records["provider_id"]
                        )
                    )
                )
            )
            db.execute(
                delete(AppointmentCancellation).where(
                    AppointmentCancellation.appointment_id.in_(
                        select(Appointment.id).where(
                            Appointment.provider_id == records["provider_id"]
                        )
                    )
                )
            )
            db.execute(
                delete(Appointment).where(
                    Appointment.provider_id == records["provider_id"]
                )
            )
            db.execute(
                delete(AppointmentSeries).where(
                    AppointmentSeries.id == records["series_id"]
                )
            )
            db.execute(
                delete(Provider).where(Provider.id == records["provider_id"])
            )
            db.execute(delete(Service).where(Service.id == records["service_id"]))
            db.execute(delete(User).where(User.id == records["owner_id"]))
            db.commit()


def test_recurring_occurrences_schedule_individual_utc_24_hour_reminders(
    recurring_reminder_records,
):
    with SessionLocal() as db:
        appointments = db.scalars(
            select(Appointment)
            .where(
                Appointment.id.in_(recurring_reminder_records["appointment_ids"])
            )
            .order_by(Appointment.occurrence_number)
        ).all()
    scheduled_calls = []

    with patch(
        "app.tasks.notification_tasks._schedule",
        side_effect=lambda task, appointment, eta: scheduled_calls.append(
            (task, appointment, eta)
        ),
    ):
        for appointment in appointments:
            schedule_appointment_notifications(appointment)

    reminder_calls = [
        (appointment, eta)
        for task, appointment, eta in scheduled_calls
        if task.name == "appointments.send_email_reminder"
    ]
    assert len(reminder_calls) == len(appointments)
    for appointment, eta in reminder_calls:
        assert eta.astimezone(UTC) == (
            appointment.appointment_start.astimezone(UTC) - timedelta(hours=24)
        )
    assert [appointment.occurrence_number for appointment, _ in reminder_calls] == [
        1,
        2,
        3,
    ]


def test_reminder_is_not_enqueued_when_24_hour_eta_is_already_past():
    appointment = type(
        "AppointmentStub",
        (),
        {
            "id": uuid4(),
            "appointment_start": datetime.now(UTC) + timedelta(hours=12),
            "appointment_end": datetime.now(UTC) + timedelta(hours=12, minutes=30),
        },
    )()

    with patch("app.tasks.notification_tasks._enqueue") as enqueue:
        schedule_appointment_notifications(appointment)

    assert all(
        call.args[0].name != "appointments.send_email_reminder"
        for call in enqueue.call_args_list
    )


def test_each_recurring_reminder_uses_contact_email_and_sent_retry_is_idempotent(
    recurring_reminder_records, monkeypatch
):
    sent = []
    monkeypatch.setattr(
        "app.services.notifications.send_email",
        lambda recipient, subject, body: sent.append((recipient, subject, body)),
    )

    with SessionLocal() as db:
        series = db.get(AppointmentSeries, recurring_reminder_records["series_id"])
        owner = db.get(User, recurring_reminder_records["owner_id"])
        appointments = db.scalars(
            select(Appointment)
            .where(Appointment.series_id == series.id)
            .order_by(Appointment.occurrence_number)
        ).all()
        assert series.customer_id == owner.id
        assert all(appointment.user_email != owner.email for appointment in appointments)
        appointment_ids = [str(appointment.id) for appointment in appointments]
        recipient_emails = [appointment.user_email for appointment in appointments]

    # The existing task retries after delivery; the SENT record prevents a resend.
    for appointment_id in appointment_ids:
        with pytest.raises(RuntimeError, match="Email reminder delivery failed"):
            send_email_reminder.run(appointment_id)
        send_email_reminder.run(appointment_id)

    assert [recipient for recipient, _, _ in sent] == recipient_emails
    assert all(subject == "Appointment reminder" for _, subject, _ in sent)
    with SessionLocal() as db:
        reminders = db.scalars(
            select(Notification).where(
                Notification.appointment_id.in_(appointment_ids),
                Notification.notification_type == NotificationType.REMINDER,
            )
        ).all()
    assert len(reminders) == 3
    assert all(reminder.status == NotificationStatus.SENT for reminder in reminders)


def test_individually_cancelled_occurrence_suppresses_only_its_reminder(
    recurring_reminder_records, monkeypatch
):
    cancelled_id, *remaining_ids = recurring_reminder_records["appointment_ids"]
    monkeypatch.setattr(
        "app.services.booking.send_cancellation_notification.delay",
        lambda _appointment_id: None,
    )
    sent = []
    monkeypatch.setattr(
        "app.services.notifications.send_email",
        lambda recipient, subject, body: sent.append(recipient),
    )

    with SessionLocal() as db:
        cancel_appointment(
            db,
            cancelled_id,
            user_role=UserRole.ADMIN,
        )

    with pytest.raises(RuntimeError, match="Email reminder delivery failed"):
        send_email_reminder.run(str(cancelled_id))
    for appointment_id in remaining_ids:
        with pytest.raises(RuntimeError, match="Email reminder delivery failed"):
            send_email_reminder.run(str(appointment_id))
        send_email_reminder.run(str(appointment_id))

    with SessionLocal() as db:
        cancelled = db.get(Appointment, cancelled_id)
        remaining = [
            db.get(Appointment, appointment_id) for appointment_id in remaining_ids
        ]
    assert cancelled.status == AppointmentStatus.CANCELLED
    assert all(item.status == AppointmentStatus.CONFIRMED for item in remaining)
    assert sent == [item.user_email for item in remaining]


def test_series_cancellation_suppresses_future_reminders_and_preserves_completed(
    recurring_reminder_records, monkeypatch
):
    monkeypatch.setattr(
        "app.services.appointment_series.send_cancellation_notification.delay",
        lambda _appointment_id: None,
    )
    completed_id, *future_ids = recurring_reminder_records["appointment_ids"]
    with SessionLocal() as db:
        completed = db.get(Appointment, completed_id)
        completed.appointment_start = datetime.now(UTC) - timedelta(days=2)
        completed.appointment_end = completed.appointment_start + timedelta(minutes=30)
        completed.status = AppointmentStatus.COMPLETED
        series = db.get(AppointmentSeries, recurring_reminder_records["series_id"])
        owner = db.get(User, recurring_reminder_records["owner_id"])
        db.commit()
        cancel_appointment_series(db, series.id, owner)

    sent = []
    monkeypatch.setattr(
        "app.services.notifications.send_email",
        lambda recipient, subject, body: sent.append(recipient),
    )
    for appointment_id in future_ids:
        with pytest.raises(RuntimeError, match="Email reminder delivery failed"):
            send_email_reminder.run(str(appointment_id))

    with SessionLocal() as db:
        completed = db.get(Appointment, completed_id)
        future = [db.get(Appointment, appointment_id) for appointment_id in future_ids]
        series = db.get(AppointmentSeries, recurring_reminder_records["series_id"])
    assert completed.status == AppointmentStatus.COMPLETED
    assert all(item.status == AppointmentStatus.CANCELLED for item in future)
    assert series.status.value == "cancelled"
    assert sent == []


def test_one_time_cancelled_appointment_reminder_remains_suppressed(
    recurring_reminder_records, monkeypatch
):
    with SessionLocal() as db:
        series = db.get(AppointmentSeries, recurring_reminder_records["series_id"])
        one_time = Appointment(
            service_id=series.service_id,
            provider_id=series.provider_id,
            customer_id=series.customer_id,
            user_name="One-time recipient",
            user_email=f"one-time-{uuid4()}@example.com",
            appointment_start=datetime.now(UTC) + timedelta(days=5),
            appointment_end=datetime.now(UTC) + timedelta(days=5, minutes=30),
            duration_minutes=30,
            buffer_time_minutes=0,
            status=AppointmentStatus.CANCELLED,
        )
        db.add(one_time)
        db.commit()
        one_time_id = one_time.id

    sent = []
    monkeypatch.setattr(
        "app.services.notifications.send_email",
        lambda recipient, subject, body: sent.append(recipient),
    )
    with pytest.raises(RuntimeError, match="Email reminder delivery failed"):
        send_email_reminder.run(str(one_time_id))
    assert sent == []
