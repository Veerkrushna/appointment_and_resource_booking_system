"""add retryable payment webhook event status

Revision ID: a1b2c3d4e5f7
Revises: d7e8f9a0b1c2
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1b2c3d4e5f7"
down_revision: str | Sequence[str] | None = "d7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE payment_webhook_event_status ADD VALUE IF NOT EXISTS 'RETRYABLE'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE payment_webhook_events "
        "SET status = 'FAILED', "
        "error_message = CASE "
        "WHEN error_message IS NULL OR BTRIM(error_message) = '' "
        "THEN 'Event was downgraded from RETRYABLE to FAILED and requires manual reconciliation.' "
        "ELSE error_message || ' | Downgraded from RETRYABLE to FAILED; manual reconciliation required.' "
        "END "
        "WHERE status = 'RETRYABLE'"
    )
    op.execute(
        "ALTER TABLE payment_webhook_events "
        "ALTER COLUMN status TYPE text USING status::text"
    )
    op.execute("DROP TYPE payment_webhook_event_status")
    op.execute(
        "CREATE TYPE payment_webhook_event_status AS ENUM "
        "('RECEIVED', 'PROCESSED', 'IGNORED', 'FAILED')"
    )
    op.execute(
        "ALTER TABLE payment_webhook_events "
        "ALTER COLUMN status TYPE payment_webhook_event_status "
        "USING status::payment_webhook_event_status"
    )
