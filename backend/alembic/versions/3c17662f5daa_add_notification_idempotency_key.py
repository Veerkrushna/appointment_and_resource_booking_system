"""add notification idempotency key

Revision ID: 3c17662f5daa
Revises: 0293c8e81454
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "3c17662f5daa"
down_revision: str | Sequence[str] | None = "0293c8e81454"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_notifications_appointment_type_idempotency_key",
        "notifications",
        ["appointment_id", "notification_type", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_notifications_appointment_type_idempotency_key",
        "notifications",
        type_="unique",
    )
    op.drop_column("notifications", "idempotency_key")
