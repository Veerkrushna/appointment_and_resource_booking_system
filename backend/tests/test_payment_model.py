from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import configure_mappers

import app.models  # noqa: F401
from app.db.database import Base, SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.appointment_series import (
    AppointmentSeries,
    AppointmentSeriesEndMode,
    AppointmentSeriesFrequency,
    AppointmentSeriesStatus,
)
from app.models.payment import Payment, PaymentProvider, PaymentStatus
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.models.service import Service, ServiceStatus
from app.models.user import User, UserRole


@pytest.fixture
def payment_records():
    db = SessionLocal()
    token = uuid4()
    customer = User(
        name=f"Payment Test {token}",
        email=f"payment-{token}@example.com",
        password_hash="test",
        role=UserRole.CUSTOMER,
    )
    provider = Provider(
        name=f"Payment Provider {token}",
        type=ProviderType.PERSON,
        email=f"provider-{token}@example.com",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    service = Service(
        name=f"Payment Service {token}",
        duration_minutes=30,
        category="Testing",
        capacity=1,
        status=ServiceStatus.ACTIVE,
    )
    db.add_all([customer, provider, service])
    db.flush()

    appointment_start = datetime.now(UTC) + timedelta(days=30)
    appointment = Appointment(
        service_id=service.id,
        provider_id=provider.id,
        customer_id=customer.id,
        user_name=customer.name,
        user_email=customer.email,
        appointment_start=appointment_start,
        appointment_end=appointment_start + timedelta(minutes=30),
        duration_minutes=30,
        status=AppointmentStatus.CONFIRMED,
    )
    series = AppointmentSeries(
        customer_id=customer.id,
        provider_id=provider.id,
        service_id=service.id,
        frequency=AppointmentSeriesFrequency.WEEKLY,
        interval=1,
        start_date=date.today() + timedelta(days=30),
        local_start_time=time(10, 0),
        timezone="UTC",
        end_mode=AppointmentSeriesEndMode.COUNT,
        occurrence_count=2,
        status=AppointmentSeriesStatus.ACTIVE,
    )
    db.add_all([appointment, series])
    db.commit()

    records = {
        "customer_id": customer.id,
        "appointment_id": appointment.id,
        "series_id": series.id,
        "service_id": service.id,
        "provider_id": provider.id,
        "token": token,
    }
    db.close()

    try:
        yield records
    finally:
        cleanup = SessionLocal()
        cleanup.execute(
            delete(Payment).where(Payment.customer_id == records["customer_id"])
        )
        cleanup.execute(
            delete(AppointmentSeries).where(
                AppointmentSeries.id == records["series_id"]
            )
        )
        cleanup.execute(
            delete(Appointment).where(Appointment.id == records["appointment_id"])
        )
        cleanup.execute(delete(User).where(User.id == records["customer_id"]))
        cleanup.execute(delete(Provider).where(Provider.id == records["provider_id"]))
        cleanup.execute(delete(Service).where(Service.id == records["service_id"]))
        cleanup.commit()
        cleanup.close()


def make_payment(
    records,
    *,
    appointment_id=None,
    series_id=None,
    provider_order_id=None,
):
    return Payment(
        customer_id=records["customer_id"],
        appointment_id=appointment_id,
        series_id=series_id,
        amount=50000,
        status=PaymentStatus.CREATED,
        provider=PaymentProvider.RAZORPAY,
        provider_order_id=provider_order_id or f"order-{uuid4()}",
    )


def test_payment_schema_constraints():
    configure_mappers()
    payment_table = Base.metadata.tables["payments"]
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in payment_table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert checks == {
        "ck_payments_not_both_appointment_and_series": (
            "appointment_id IS NULL OR series_id IS NULL"
        )
    }
    unique_constraints = {
        constraint.name: [column.name for column in constraint.columns]
        for constraint in payment_table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert unique_constraints == {
        "uq_payments_appointment_id": ["appointment_id"],
        "uq_payments_series_id": ["series_id"],
        "uq_payments_provider_order_id": ["provider_order_id"],
    }


def test_payment_without_booking_is_valid_before_booking(payment_records):
    db = SessionLocal()
    payment = make_payment(payment_records)
    db.add(payment)
    db.commit()
    assert payment.status is PaymentStatus.CREATED
    assert payment.appointment_id is None
    assert payment.series_id is None
    assert payment.amount == 50000
    assert payment.currency == "INR"
    db.close()


def test_payment_can_exist_before_provider_order_creation(payment_records):
    db = SessionLocal()
    payment = make_payment(payment_records)
    payment.provider_order_id = None
    db.add(payment)
    db.commit()
    assert payment.provider_order_id is None
    db.close()


def test_captured_payment_can_precede_booking_creation(payment_records):
    db = SessionLocal()
    payment = make_payment(payment_records)
    payment.status = PaymentStatus.CAPTURED
    db.add(payment)
    db.commit()
    assert payment.appointment_id is None
    assert payment.series_id is None
    db.close()


def test_prebooking_payment_can_be_linked_to_appointment(payment_records):
    db = SessionLocal()
    payment = make_payment(payment_records)
    db.add(payment)
    db.commit()

    payment.appointment_id = payment_records["appointment_id"]
    db.commit()

    assert payment.appointment_id == payment_records["appointment_id"]
    assert payment.series_id is None
    db.close()


@pytest.mark.parametrize("booking_field", ["appointment_id", "series_id"])
def test_payment_with_exactly_one_booking_is_valid(payment_records, booking_field):
    db = SessionLocal()
    payment = make_payment(
        payment_records,
        **{booking_field: payment_records[booking_field]},
    )
    db.add(payment)
    db.commit()
    assert getattr(payment, booking_field) == payment_records[booking_field]
    db.close()


def test_payment_cannot_reference_appointment_and_series(payment_records):
    db = SessionLocal()
    db.add(
        make_payment(
            payment_records,
            appointment_id=payment_records["appointment_id"],
            series_id=payment_records["series_id"],
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.close()


@pytest.mark.parametrize("booking_field", ["appointment_id", "series_id"])
def test_booking_has_at_most_one_payment(payment_records, booking_field):
    db = SessionLocal()
    value = payment_records[booking_field]
    db.add(make_payment(payment_records, **{booking_field: value}))
    db.commit()

    duplicate = make_payment(payment_records, **{booking_field: value})
    with pytest.raises(IntegrityError):
        db.add(duplicate)
        db.commit()
    db.rollback()
    db.close()


def test_provider_order_id_is_unique(payment_records):
    db = SessionLocal()
    provider_order_id = f"order-{payment_records['token']}"
    db.add(make_payment(payment_records, provider_order_id=provider_order_id))
    db.commit()

    db.add(
        make_payment(
            payment_records,
            appointment_id=payment_records["appointment_id"],
            provider_order_id=provider_order_id,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.close()
