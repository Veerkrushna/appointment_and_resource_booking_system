from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import configure_mappers

import app.models  # noqa: F401
from app.db.database import Base
from app.models.appointment import Appointment
from app.models.appointment_series import (
    AppointmentSeries,
    AppointmentSeriesEndMode,
    AppointmentSeriesFrequency,
    AppointmentSeriesStatus,
)


def test_appointment_series_schema_metadata():
    configure_mappers()
    series_table = AppointmentSeries.__table__
    appointment_table = Appointment.__table__

    assert Base.metadata.tables["appointment_series"] is series_table
    assert series_table.c.id.primary_key
    assert series_table.c.customer_id.nullable
    assert not series_table.c.provider_id.nullable
    assert not series_table.c.service_id.nullable
    assert series_table.c.frequency.type.enums == ["WEEKLY", "MONTHLY"]
    assert series_table.c.end_mode.type.enums == ["COUNT", "END_DATE"]
    assert series_table.c.status.type.enums == ["ACTIVE", "CANCELLED"]
    series_foreign_keys = {
        foreign_key.constraint.name: (
            foreign_key.target_fullname,
            foreign_key.ondelete,
        )
        for column in series_table.columns
        for foreign_key in column.foreign_keys
    }
    assert series_foreign_keys == {
        "fk_appointment_series_customer_id": ("users.id", "SET NULL"),
        "fk_appointment_series_provider_id": ("providers.id", "CASCADE"),
        "fk_appointment_series_service_id": ("services.id", "RESTRICT"),
    }
    assert {
        "ix_appointment_series_customer_id",
        "ix_appointment_series_provider_start",
    } <= {index.name for index in series_table.indexes}
    series_appointment_relationship = AppointmentSeries.appointments.property
    assert series_appointment_relationship.passive_deletes == "all"
    assert "delete-orphan" not in series_appointment_relationship.cascade

    series_checks = {
        constraint.name
        for constraint in series_table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert {
        "ck_appointment_series_occurrence_count_range",
        "ck_appointment_series_end_condition",
        "ck_appointment_series_end_date_after_start",
        "ck_appointment_series_frequency_interval",
    } <= series_checks

    assert appointment_table.c.series_id.nullable
    assert appointment_table.c.occurrence_number.nullable
    assert not appointment_table.c.buffer_time_minutes.nullable
    assert appointment_table.c.buffer_time_minutes.server_default.arg == "0"
    appointment_series_foreign_key = next(
        foreign_key for foreign_key in appointment_table.c.series_id.foreign_keys
    )
    assert appointment_series_foreign_key.target_fullname == "appointment_series.id"
    assert appointment_series_foreign_key.ondelete == "RESTRICT"
    appointment_constraints = {
        constraint.name: constraint for constraint in appointment_table.constraints
    }
    assert "ck_appointment_series_occurrence_pair" in appointment_constraints
    assert "ck_appointment_buffer_time_nonnegative" in appointment_constraints
    unique_constraint = appointment_constraints["uq_appointments_series_occurrence"]
    assert isinstance(unique_constraint, UniqueConstraint)
    assert [column.name for column in unique_constraint.columns] == [
        "series_id",
        "occurrence_number",
    ]

    assert AppointmentSeriesFrequency.WEEKLY.value == "weekly"
    assert AppointmentSeriesEndMode.COUNT.value == "count"
    assert AppointmentSeriesStatus.ACTIVE.value == "active"
