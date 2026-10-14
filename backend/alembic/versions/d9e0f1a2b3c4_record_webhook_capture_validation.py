"""record structured webhook capture validation evidence

Revision ID: d9e0f1a2b3c4
Revises: c4d5e6f7a8b9
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: str | Sequence[str] | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payment_webhook_events",
        sa.Column("capture_validation_failure", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "payment_webhook_events",
        sa.Column("capture_validation_details", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payment_webhook_events", "capture_validation_details")
    op.drop_column("payment_webhook_events", "capture_validation_failure")
