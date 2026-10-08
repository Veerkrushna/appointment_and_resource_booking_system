"""make payment provider order ID nullable

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: str | Sequence[str] | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "payments",
        "provider_order_id",
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS ("
        "SELECT 1 FROM payments WHERE provider_order_id IS NULL"
        ") THEN "
        "RAISE EXCEPTION "
        "'Cannot make payments.provider_order_id NOT NULL while NULL values exist'; "
        "END IF; "
        "END $$"
    )
    op.alter_column(
        "payments",
        "provider_order_id",
        existing_type=sa.String(length=255),
        nullable=False,
    )
