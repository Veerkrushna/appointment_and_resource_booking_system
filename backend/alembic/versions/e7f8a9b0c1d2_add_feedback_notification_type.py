"""add feedback request notification type

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | Sequence[str] | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'FEEDBACK_REQUEST'"
    )


def downgrade() -> None:
    pass