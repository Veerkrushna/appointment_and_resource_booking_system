from datetime import UTC, datetime, time
from decimal import Decimal

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.appointment_cancellation import AppointmentCancellation
from app.models.availability import (
    ProviderAvailability,
    ProviderBlackoutDate,
    ProviderBreak,
)
from app.models.notification import Notification
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.service import Service, ServiceStatus


def clear_database(db):
    db.execute(delete(Notification))
    db.execute(delete(AppointmentCancellation))
    db.execute(delete(Appointment))
    db.execute(delete(ProviderBlackoutDate))
    db.execute(delete(ProviderBreak))
    db.execute(delete(ProviderAvailability))
    db.execute(delete(ProviderService))
    db.execute(delete(Provider))
    db.execute(delete(Service))

    print("Database cleared successfully.")


def create_services(db):
    services = [
        Service(
            name="General Consultation",
            description="A 30-minute consultation with a qualified provider.",
            duration_minutes=30,
            price=Decimal("500.00"),
            category="Consultation",
            capacity=1,
            buffer_time_minutes=10,
            status=ServiceStatus.ACTIVE,
        ),
        Service(
            name="Follow-up Consultation",
            description="A short follow-up session to review progress and next steps.",
            duration_minutes=20,
            price=Decimal("300.00"),
            category="Consultation",
            capacity=1,
            buffer_time_minutes=5,
            status=ServiceStatus.ACTIVE,
        ),
        Service(
            name="Specialist Consultation",
            description="A detailed consultation with a specialist provider.",
            duration_minutes=45,
            price=Decimal("800.00"),
            category="Specialist",
            capacity=1,
            buffer_time_minutes=10,
            status=ServiceStatus.ACTIVE,
        ),
        Service(
            name="Therapy Session",
            description="A one-hour private session with a qualified therapist.",
            duration_minutes=60,
            price=Decimal("1000.00"),
            category="Therapy",
            capacity=1,
            buffer_time_minutes=15,
            status=ServiceStatus.ACTIVE,
        ),
    ]

    db.add_all(services)
    db.flush()

    print(f"Created {len(services)} services.")

    return services


def create_providers(db):
    providers = [
        Provider(
            name="Dr. Ananya Sharma",
            type=ProviderType.PERSON,
            email="ananya.sharma@example.com",
            phone="+919876543210",
            timezone="Asia/Kolkata",
            availability_status=AvailabilityStatus.AVAILABLE,
        ),
        Provider(
            name="Dr. Rahul Mehta",
            type=ProviderType.PERSON,
            email="rahul.mehta@example.com",
            phone="+919876543211",
            timezone="Asia/Kolkata",
            availability_status=AvailabilityStatus.AVAILABLE,
        ),
        Provider(
            name="Dr. Priya Nair",
            type=ProviderType.PERSON,
            email="priya.nair@example.com",
            phone="+919876543212",
            timezone="Asia/Kolkata",
            availability_status=AvailabilityStatus.AVAILABLE,
        ),
        Provider(
            name="Consultation Room 1",
            type=ProviderType.RESOURCE,
            email="room1@example.com",
            phone=None,
            timezone="Asia/Kolkata",
            availability_status=AvailabilityStatus.AVAILABLE,
        ),
    ]

    db.add_all(providers)
    db.flush()

    print(f"Created {len(providers)} providers.")

    return providers


def create_provider_services(db, providers, services):
    links = [
        # Dr. Ananya Sharma
        ProviderService(
            provider_id=providers[0].id,
            service_id=services[0].id,  # General Consultation
        ),
        ProviderService(
            provider_id=providers[0].id,
            service_id=services[1].id,  # Follow-up Consultation
        ),
        # Dr. Rahul Mehta
        ProviderService(
            provider_id=providers[1].id,
            service_id=services[0].id,  # General Consultation
        ),
        ProviderService(
            provider_id=providers[1].id,
            service_id=services[2].id,  # Specialist Consultation
        ),
        # Dr. Priya Nair
        ProviderService(
            provider_id=providers[2].id,
            service_id=services[1].id,  # Follow-up Consultation
        ),
        ProviderService(
            provider_id=providers[2].id,
            service_id=services[3].id,  # Therapy Session
        ),
        # Consultation Room 1
        ProviderService(
            provider_id=providers[3].id,
            service_id=services[0].id,  # General Consultation
        ),
    ]

    db.add_all(links)
    db.flush()

    print(f"Created {len(links)} provider-service relationships.")

    return links


from datetime import time


def create_availability(db, providers):
    availability = []

    # Monday to Friday: 09:00 - 17:00
    for provider in providers:
        for day in range(5):
            availability.append(
                ProviderAvailability(
                    provider_id=provider.id,
                    day_of_week=day,
                    start_time=time(9, 0),
                    end_time=time(17, 0),
                    is_working_day=True,
                )
            )

        # Saturday: off
        availability.append(
            ProviderAvailability(
                provider_id=provider.id,
                day_of_week=5,
                start_time=None,
                end_time=None,
                is_working_day=False,
            )
        )

        # Sunday: off
        availability.append(
            ProviderAvailability(
                provider_id=provider.id,
                day_of_week=6,
                start_time=None,
                end_time=None,
                is_working_day=False,
            )
        )

    db.add_all(availability)
    db.flush()

    print(f"Created {len(availability)} weekly availability records.")

    return availability


def create_breaks(db, providers):
    breaks = []

    for provider in providers:
        # Lunch break: Monday to Friday
        for day in range(5):
            breaks.append(
                ProviderBreak(
                    provider_id=provider.id,
                    day_of_week=day,
                    start_time=time(13, 0),
                    end_time=time(14, 0),
                    break_type="Lunch",
                )
            )

    db.add_all(breaks)
    db.flush()

    print(f"Created {len(breaks)} weekly break records.")

    return breaks


from datetime import UTC, datetime


def create_blackout_dates(db, providers):
    blackout_dates = [
        ProviderBlackoutDate(
            provider_id=providers[0].id,
            blackout_start=datetime(2026, 9, 21, 0, 0, tzinfo=UTC),
            blackout_end=datetime(2026, 9, 21, 23, 59, 59, tzinfo=UTC),
            reason="Personal leave",
            is_all_day=True,
        ),
        ProviderBlackoutDate(
            provider_id=providers[1].id,
            blackout_start=datetime(2026, 9, 25, 0, 0, tzinfo=UTC),
            blackout_end=datetime(2026, 9, 25, 23, 59, 59, tzinfo=UTC),
            reason="Professional conference",
            is_all_day=True,
        ),
        ProviderBlackoutDate(
            provider_id=providers[2].id,
            blackout_start=datetime(2026, 9, 30, 0, 0, tzinfo=UTC),
            blackout_end=datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC),
            reason="Leave",
            is_all_day=True,
        ),
    ]

    db.add_all(blackout_dates)
    db.flush()

    print(f"Created {len(blackout_dates)} blackout dates.")

    return blackout_dates


def create_appointments(db, providers, services):
    appointments = [
        Appointment(
            service_id=services[0].id,
            provider_id=providers[0].id,
            user_name="Aarav Patel",
            user_email="aarav.patel@example.com",
            user_phone="+919800000001",
            appointment_start=datetime(2026, 9, 16, 10, 0, tzinfo=UTC),
            appointment_end=datetime(2026, 9, 16, 10, 30, tzinfo=UTC),
            duration_minutes=30,
            notes="Initial consultation",
            status=AppointmentStatus.CONFIRMED,
        ),
        Appointment(
            service_id=services[1].id,
            provider_id=providers[2].id,
            user_name="Meera Shah",
            user_email="meera.shah@example.com",
            user_phone="+919800000002",
            appointment_start=datetime(2026, 9, 17, 11, 0, tzinfo=UTC),
            appointment_end=datetime(2026, 9, 17, 11, 20, tzinfo=UTC),
            duration_minutes=20,
            notes="Follow-up appointment",
            status=AppointmentStatus.PENDING,
        ),
        Appointment(
            service_id=services[2].id,
            provider_id=providers[1].id,
            user_name="Rohan Deshmukh",
            user_email="rohan.deshmukh@example.com",
            user_phone="+919800000003",
            appointment_start=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
            appointment_end=datetime(2026, 9, 14, 10, 45, tzinfo=UTC),
            duration_minutes=45,
            notes="Specialist consultation",
            status=AppointmentStatus.COMPLETED,
        ),
        Appointment(
            service_id=services[3].id,
            provider_id=providers[2].id,
            user_name="Kavya Joshi",
            user_email="kavya.joshi@example.com",
            user_phone="+919800000004",
            appointment_start=datetime(2026, 9, 18, 15, 0, tzinfo=UTC),
            appointment_end=datetime(2026, 9, 18, 16, 0, tzinfo=UTC),
            duration_minutes=60,
            notes="Therapy session",
            status=AppointmentStatus.CANCELLED,
        ),
    ]

    db.add_all(appointments)
    db.flush()

    print(f"Created {len(appointments)} appointments.")

    return appointments


def seed_database():
    db = SessionLocal()

    try:
        clear_database(db)

        services = create_services(db)
        providers = create_providers(db)

        create_provider_services(db, providers, services)
        create_availability(db, providers)
        create_breaks(db, providers)
        create_blackout_dates(db, providers)
        create_appointments(db, providers, services)

        db.commit()

        print("Database seeded successfully.")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
