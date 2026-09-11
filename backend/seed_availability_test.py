from datetime import datetime, time
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.db.database import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.availability import (
    ProviderAvailability,
    ProviderBlackoutDate,
    ProviderBreak,
)
from app.models.provider_service import ProviderService
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.service import Service, ServiceStatus


def seed():
    db = SessionLocal()

    try:
        # ---------------------------------------------------------
        # SERVICES
        # ---------------------------------------------------------

        consultation = Service(
            id=uuid4(),
            name="General Consultation",
            description="30 minute consultation",
            duration_minutes=30,
            price=500,
            category="Consultation",
            capacity=1,
            buffer_time_minutes=10,
            status=ServiceStatus.ACTIVE,
        )

        therapy = Service(
            id=uuid4(),
            name="Therapy Session",
            description="60 minute therapy session",
            duration_minutes=60,
            price=1000,
            category="Therapy",
            capacity=1,
            buffer_time_minutes=15,
            status=ServiceStatus.ACTIVE,
        )

        db.add_all([consultation, therapy])
        db.flush()

        # ---------------------------------------------------------
        # PROVIDERS
        # ---------------------------------------------------------

        provider_1 = Provider(
            id=uuid4(),
            name="Dr. Rahul Sharma",
            type=ProviderType.PERSON,
            email="rahul@example.com",
            phone="9876543210",
            timezone="Asia/Kolkata",
            availability_status=AvailabilityStatus.AVAILABLE,
        )

        provider_2 = Provider(
            id=uuid4(),
            name="Dr. Priya Mehta",
            type=ProviderType.PERSON,
            email="priya@example.com",
            phone="9876543211",
            timezone="Asia/Kolkata",
            availability_status=AvailabilityStatus.AVAILABLE,
        )

        provider_3 = Provider(
            id=uuid4(),
            name="Consultation Room A",
            type=ProviderType.RESOURCE,
            email="room-a@example.com",
            phone=None,
            timezone="Asia/Kolkata",
            availability_status=AvailabilityStatus.AVAILABLE,
        )

        db.add_all([provider_1, provider_2, provider_3])
        db.flush()

        # ---------------------------------------------------------
        # PROVIDER ↔ SERVICE
        # ---------------------------------------------------------

        db.add_all(
            [
                # Rahul provides both
                ProviderService(
                    provider_id=provider_1.id,
                    service_id=consultation.id,
                    is_active=True,
                ),
                ProviderService(
                    provider_id=provider_1.id,
                    service_id=therapy.id,
                    is_active=True,
                ),
                # Priya provides both
                ProviderService(
                    provider_id=provider_2.id,
                    service_id=consultation.id,
                    is_active=True,
                ),
                ProviderService(
                    provider_id=provider_2.id,
                    service_id=therapy.id,
                    is_active=True,
                ),
                # Room A only provides consultation
                ProviderService(
                    provider_id=provider_3.id,
                    service_id=consultation.id,
                    is_active=True,
                ),
            ]
        )

        # ---------------------------------------------------------
        # WEEKLY AVAILABILITY
        #
        # Monday-Friday: 09:00 - 17:00
        # Saturday/Sunday: not working
        # ---------------------------------------------------------

        providers = [provider_1, provider_2, provider_3]

        for provider in providers:
            for day in range(7):
                if day < 5:
                    db.add(
                        ProviderAvailability(
                            provider_id=provider.id,
                            day_of_week=day,
                            start_time=time(9, 0),
                            end_time=time(17, 0),
                            is_working_day=True,
                        )
                    )
                else:
                    db.add(
                        ProviderAvailability(
                            provider_id=provider.id,
                            day_of_week=day,
                            start_time=None,
                            end_time=None,
                            is_working_day=False,
                        )
                    )

        # ---------------------------------------------------------
        # BREAKS
        #
        # Lunch: 13:00 - 14:00 every weekday
        # ---------------------------------------------------------

        for provider in providers:
            for day in range(5):
                db.add(
                    ProviderBreak(
                        provider_id=provider.id,
                        day_of_week=day,
                        start_time=time(13, 0),
                        end_time=time(14, 0),
                        break_type="Lunch",
                    )
                )

        db.flush()

        # ---------------------------------------------------------
        # BLACKOUT
        #
        # Rahul unavailable on 2026-09-17 from 09:00-17:00
        # ---------------------------------------------------------

        ist = ZoneInfo("Asia/Kolkata")

        db.add(
            ProviderBlackoutDate(
                provider_id=provider_1.id,
                blackout_start=datetime(2026, 9, 17, 9, 0, tzinfo=ist),
                blackout_end=datetime(2026, 9, 17, 17, 0, tzinfo=ist),
                reason="Personal leave",
                is_all_day=True,
            )
        )

        # ---------------------------------------------------------
        # APPOINTMENTS
        #
        # Rahul:
        #   Sep 15: 10:00-10:30
        #   Sep 16: 14:30-15:00
        #
        # Priya:
        #   Sep 15: 11:00-11:30
        #   Sep 17: 15:00-15:30
        # ---------------------------------------------------------

        db.add_all(
            [
                Appointment(
                    id=uuid4(),
                    service_id=consultation.id,
                    provider_id=provider_1.id,
                    user_name="Test User 1",
                    user_email="test1@example.com",
                    user_phone="9000000001",
                    appointment_start=datetime(2026, 9, 15, 10, 0, tzinfo=ist),
                    appointment_end=datetime(2026, 9, 15, 10, 30, tzinfo=ist),
                    duration_minutes=30,
                    status=AppointmentStatus.CONFIRMED,
                ),
                Appointment(
                    id=uuid4(),
                    service_id=consultation.id,
                    provider_id=provider_1.id,
                    user_name="Test User 2",
                    user_email="test2@example.com",
                    user_phone="9000000002",
                    appointment_start=datetime(2026, 9, 16, 14, 30, tzinfo=ist),
                    appointment_end=datetime(2026, 9, 16, 15, 0, tzinfo=ist),
                    duration_minutes=30,
                    status=AppointmentStatus.CONFIRMED,
                ),
                Appointment(
                    id=uuid4(),
                    service_id=consultation.id,
                    provider_id=provider_2.id,
                    user_name="Test User 3",
                    user_email="test3@example.com",
                    user_phone="9000000003",
                    appointment_start=datetime(2026, 9, 15, 11, 0, tzinfo=ist),
                    appointment_end=datetime(2026, 9, 15, 11, 30, tzinfo=ist),
                    duration_minutes=30,
                    status=AppointmentStatus.CONFIRMED,
                ),
                Appointment(
                    id=uuid4(),
                    service_id=consultation.id,
                    provider_id=provider_2.id,
                    user_name="Test User 4",
                    user_email="test4@example.com",
                    user_phone="9000000004",
                    appointment_start=datetime(2026, 9, 17, 15, 0, tzinfo=ist),
                    appointment_end=datetime(2026, 9, 17, 15, 30, tzinfo=ist),
                    duration_minutes=30,
                    status=AppointmentStatus.CONFIRMED,
                ),
            ]
        )

        db.commit()

        print("\n========================================")
        print("TEST DATA CREATED")
        print("========================================\n")

        print("SERVICES")
        print(f"General Consultation: {consultation.id}")
        print(f"Therapy Session:       {therapy.id}")

        print("\nPROVIDERS")
        print(f"Rahul Sharma:  {provider_1.id}")
        print(f"Priya Mehta:   {provider_2.id}")
        print(f"Room A:        {provider_3.id}")

        print("\n========================================")
        print("IMPORTANT IDS FOR TESTING")
        print("========================================")
        print(f"SERVICE_ID={consultation.id}")
        print(f"THERAPY_ID={therapy.id}")
        print(f"PROVIDER_1_ID={provider_1.id}")
        print(f"PROVIDER_2_ID={provider_2.id}")
        print(f"PROVIDER_3_ID={provider_3.id}")
        print("========================================\n")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed()
