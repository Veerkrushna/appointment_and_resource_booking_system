"""record local payment-state conflicts from capture webhooks

Revision ID: e1f2a3b4c5d6
Revises: d9e0f1a2b3c4
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payment_webhook_events",
        sa.Column(
            "local_payment_state_conflict",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("payment_webhook_events", "local_payment_state_conflict")
