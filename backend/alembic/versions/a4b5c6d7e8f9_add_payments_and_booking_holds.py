"""add payments and booking holds

Revision ID: a4b5c6d7e8f9
Revises: c223c51abc8a, f1a2b3c4d5e6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: str | Sequence[str] | None = (
    "c223c51abc8a",
    "f1a2b3c4d5e6",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE payment_status AS ENUM "
        "('CREATED', 'PENDING', 'CAPTURED', 'FAILED', 'REFUNDED', 'PARTIALLY_REFUNDED')"
    )
    op.execute("CREATE TYPE payment_provider AS ENUM ('RAZORPAY')")
    op.execute(
        "CREATE TYPE booking_hold_status AS ENUM "
        "('ACTIVE', 'CONVERTED', 'EXPIRED', 'RELEASED')"
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("appointment_id", sa.UUID(), nullable=True),
        sa.Column("series_id", sa.UUID(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default="INR",
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "CREATED",
                "PENDING",
                "CAPTURED",
                "FAILED",
                "REFUNDED",
                "PARTIALLY_REFUNDED",
                name="payment_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "provider",
            postgresql.ENUM(
                "RAZORPAY",
                name="payment_provider",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("provider_order_id", sa.String(length=255), nullable=False),
        sa.Column("provider_payment_id", sa.String(length=255), nullable=True),
        sa.Column("provider_signature", sa.String(length=255), nullable=True),
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
            "(appointment_id IS NOT NULL) <> (series_id IS NOT NULL)",
            name="ck_payments_appointment_or_series",
        ),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["series_id"], ["appointment_series.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("appointment_id", name="uq_payments_appointment_id"),
        sa.UniqueConstraint("provider_order_id", name="uq_payments_provider_order_id"),
        sa.UniqueConstraint("series_id", name="uq_payments_series_id"),
    )
    op.create_index("ix_payments_customer_id", "payments", ["customer_id"])
    op.create_index("ix_payments_status", "payments", ["status"])

    op.create_table(
        "booking_holds",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("appointment_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("appointment_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "CONVERTED",
                "EXPIRED",
                "RELEASED",
                name="booking_hold_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("payment_id", sa.UUID(), nullable=True),
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
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_booking_holds_provider_id", "booking_holds", ["provider_id"])
    op.create_index(
        "ix_booking_holds_appointment_start",
        "booking_holds",
        ["appointment_start"],
    )
    op.create_index(
        "ix_booking_holds_appointment_end",
        "booking_holds",
        ["appointment_end"],
    )
    op.create_index("ix_booking_holds_expires_at", "booking_holds", ["expires_at"])
    op.create_index("ix_booking_holds_status", "booking_holds", ["status"])
    op.create_index("ix_booking_holds_payment_id", "booking_holds", ["payment_id"])


def downgrade() -> None:
    op.drop_index("ix_booking_holds_payment_id", table_name="booking_holds")
    op.drop_index("ix_booking_holds_status", table_name="booking_holds")
    op.drop_index("ix_booking_holds_expires_at", table_name="booking_holds")
    op.drop_index("ix_booking_holds_appointment_end", table_name="booking_holds")
    op.drop_index("ix_booking_holds_appointment_start", table_name="booking_holds")
    op.drop_index("ix_booking_holds_provider_id", table_name="booking_holds")
    op.drop_table("booking_holds")

    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_customer_id", table_name="payments")
    op.drop_table("payments")

    op.execute("DROP TYPE booking_hold_status")
    op.execute("DROP TYPE payment_provider")
    op.execute("DROP TYPE payment_status")
