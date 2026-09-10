"""add reschedule notification type

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: str | Sequence[str] | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'RESCHEDULE'"
    )


def downgrade() -> None:
    pass
