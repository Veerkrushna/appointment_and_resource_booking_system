"""create appointments table

Revision ID: a1b2c3d4e5f6
Revises: 99a0328f6aa9
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "99a0328f6aa9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "appointments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("user_name", sa.String(length=255), nullable=False),
        sa.Column("user_email", sa.String(length=320), nullable=False),
        sa.Column("user_phone", sa.String(length=30), nullable=True),
        sa.Column("appointment_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("appointment_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "CONFIRMED",
                "COMPLETED",
                "CANCELLED",
                name="appointment_status",
            ),
            nullable=False,
        ),
        sa.Column("confirmation_token", sa.String(length=255), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
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
            "appointment_end > appointment_start",
            name="ck_appointment_end_after_start",
        ),
        sa.CheckConstraint(
            "duration_minutes > 0", name="ck_appointment_duration_positive"
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["providers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["service_id"], ["services.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("confirmation_token"),
    )
    op.create_index(
        "ix_appointments_provider_start",
        "appointments",
        ["provider_id", "appointment_start"],
    )
    op.create_index(
        "ix_appointments_user_email", "appointments", ["user_email"]
    )
    op.create_index(
        "ix_appointments_status_start",
        "appointments",
        ["status", "appointment_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_appointments_status_start", table_name="appointments")
    op.drop_index("ix_appointments_user_email", table_name="appointments")
    op.drop_index("ix_appointments_provider_start", table_name="appointments")
    op.drop_table("appointments")
    sa.Enum(name="appointment_status").drop(op.get_bind(), checkfirst=True)