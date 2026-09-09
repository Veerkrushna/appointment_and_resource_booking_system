"""add provider timezone

Revision ID: d6e7f8a9b0c1
Revises: b5bcaeccf96f
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: str | Sequence[str] | None = "b5bcaeccf96f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "providers",
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("providers", "timezone")