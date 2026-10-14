"""add retryable webhook event status

Revision ID: f2a3b4c5d6e7
Revises: e8f9a0b1c2d3
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | Sequence[str] | None = "e8f9a0b1c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE payment_webhook_event_status ADD VALUE 'RETRYABLE' BEFORE 'FAILED'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE payment_webhook_events SET status = 'FAILED' "
        "WHERE status = 'RETRYABLE'"
    )
    op.execute(
        "ALTER TYPE payment_webhook_event_status "
        "RENAME TO payment_webhook_event_status_old"
    )
    op.execute(
        "CREATE TYPE payment_webhook_event_status AS ENUM "
        "('RECEIVED', 'PROCESSED', 'IGNORED', 'FAILED')"
    )
    op.execute(
        "ALTER TABLE payment_webhook_events ALTER COLUMN status "
        "TYPE payment_webhook_event_status USING status::text::payment_webhook_event_status"
    )
    op.execute("DROP TYPE payment_webhook_event_status_old")
