"""add recipient snapshot to booking holds

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8f9a0b1c2d3"
down_revision: str | Sequence[str] | None = "d7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "booking_holds", sa.Column("user_name", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "booking_holds", sa.Column("user_email", sa.String(length=320), nullable=True)
    )
    op.add_column(
        "booking_holds", sa.Column("user_phone", sa.String(length=30), nullable=True)
    )
    op.add_column("booking_holds", sa.Column("notes", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE booking_holds
        SET user_name = users.name,
            user_email = users.email,
            user_phone = users.phone
        FROM users
        WHERE booking_holds.customer_id = users.id
        """
    )
    op.alter_column("booking_holds", "user_name", nullable=False)
    op.alter_column("booking_holds", "user_email", nullable=False)


def downgrade() -> None:
    op.drop_column("booking_holds", "notes")
    op.drop_column("booking_holds", "user_phone")
    op.drop_column("booking_holds", "user_email")
    op.drop_column("booking_holds", "user_name")
