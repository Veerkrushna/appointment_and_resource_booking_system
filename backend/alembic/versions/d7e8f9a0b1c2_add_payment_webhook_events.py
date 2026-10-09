"""add payment webhook events

Revision ID: d7e8f9a0b1c2
Revises: c5d6e7f8a9b0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d7e8f9a0b1c2"
down_revision: str | Sequence[str] | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE payment_webhook_event_status AS ENUM "
        "('RECEIVED', 'PROCESSED', 'IGNORED', 'FAILED')"
    )
    op.create_table(
        "payment_webhook_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("provider_order_id", sa.String(length=255), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "RECEIVED",
                "PROCESSED",
                "IGNORED",
                "FAILED",
                name="payment_webhook_event_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_event_id",
            name="uq_payment_webhook_events_provider_event_id",
        ),
    )
    op.create_index(
        "ix_payment_webhook_events_status",
        "payment_webhook_events",
        ["status"],
    )
    op.create_index(
        "ix_payment_webhook_events_created_at",
        "payment_webhook_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_webhook_events_created_at",
        table_name="payment_webhook_events",
    )
    op.drop_index(
        "ix_payment_webhook_events_status",
        table_name="payment_webhook_events",
    )
    op.drop_table("payment_webhook_events")
    op.execute("DROP TYPE payment_webhook_event_status")
