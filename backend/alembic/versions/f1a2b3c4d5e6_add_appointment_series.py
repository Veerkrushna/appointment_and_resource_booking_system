"""add appointment series and appointment recurrence links

Revision ID: f1a2b3c4d5e6
Revises: a9c8f1d2e3b4
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "a9c8f1d2e3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE appointment_series_frequency AS ENUM ('WEEKLY', 'MONTHLY')")
    op.execute("CREATE TYPE appointment_series_end_mode AS ENUM ('COUNT', 'END_DATE')")
    op.execute("CREATE TYPE appointment_series_status AS ENUM ('ACTIVE', 'CANCELLED')")

    op.create_table(
        "appointment_series",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column(
            "frequency",
            postgresql.ENUM(
                "WEEKLY",
                "MONTHLY",
                name="appointment_series_frequency",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("interval", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("local_start_time", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column(
            "end_mode",
            postgresql.ENUM(
                "COUNT",
                "END_DATE",
                name="appointment_series_end_mode",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("occurrence_count", sa.Integer(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "CANCELLED",
                name="appointment_series_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "occurrence_count IS NULL OR occurrence_count BETWEEN 1 AND 52",
            name="ck_appointment_series_occurrence_count_range",
        ),
        sa.CheckConstraint(
            "(end_mode = 'COUNT' AND occurrence_count IS NOT NULL AND end_date IS NULL) "
            "OR (end_mode = 'END_DATE' AND occurrence_count IS NULL AND end_date IS NOT NULL)",
            name="ck_appointment_series_end_condition",
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_appointment_series_end_date_after_start",
        ),
        sa.CheckConstraint(
            "(frequency = 'WEEKLY' AND interval IN (1, 2)) "
            "OR (frequency = 'MONTHLY' AND interval = 1)",
            name="ck_appointment_series_frequency_interval",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["users.id"],
            name="fk_appointment_series_customer_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["providers.id"],
            name="fk_appointment_series_provider_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name="fk_appointment_series_service_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_appointment_series_customer_id",
        "appointment_series",
        ["customer_id"],
    )
    op.create_index(
        "ix_appointment_series_provider_start",
        "appointment_series",
        ["provider_id", "start_date"],
    )

    op.add_column(
        "appointments",
        sa.Column(
            "buffer_time_minutes",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE appointments AS appointment "
        "SET buffer_time_minutes = COALESCE(service.buffer_time_minutes, 0) "
        "FROM services AS service "
        "WHERE appointment.service_id = service.id"
    )
    op.execute(
        "UPDATE appointments SET buffer_time_minutes = 0 "
        "WHERE buffer_time_minutes IS NULL"
    )
    op.alter_column(
        "appointments",
        "buffer_time_minutes",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
    )

    op.add_column("appointments", sa.Column("series_id", sa.UUID(), nullable=True))
    op.add_column(
        "appointments", sa.Column("occurrence_number", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_appointments_series_id",
        "appointments",
        "appointment_series",
        ["series_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_appointment_buffer_time_nonnegative",
        "appointments",
        "buffer_time_minutes >= 0",
    )
    op.create_check_constraint(
        "ck_appointment_series_occurrence_pair",
        "appointments",
        "(series_id IS NULL AND occurrence_number IS NULL) "
        "OR (series_id IS NOT NULL AND occurrence_number IS NOT NULL AND occurrence_number > 0)",
    )
    op.create_unique_constraint(
        "uq_appointments_series_occurrence",
        "appointments",
        ["series_id", "occurrence_number"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_appointments_series_occurrence", "appointments", type_="unique"
    )
    op.drop_constraint(
        "ck_appointment_series_occurrence_pair", "appointments", type_="check"
    )
    op.drop_constraint(
        "ck_appointment_buffer_time_nonnegative", "appointments", type_="check"
    )
    op.drop_constraint("fk_appointments_series_id", "appointments", type_="foreignkey")
    op.drop_column("appointments", "occurrence_number")
    op.drop_column("appointments", "series_id")
    op.drop_column("appointments", "buffer_time_minutes")

    op.drop_index(
        "ix_appointment_series_provider_start", table_name="appointment_series"
    )
    op.drop_index("ix_appointment_series_customer_id", table_name="appointment_series")
    op.drop_table("appointment_series")

    op.execute("DROP TYPE appointment_series_status")
    op.execute("DROP TYPE appointment_series_end_mode")
    op.execute("DROP TYPE appointment_series_frequency")
