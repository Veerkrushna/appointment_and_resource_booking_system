"""store webhook refund identifier

Revision ID: 0293c8e81454
Revises: 3c152cef51bb
Create Date: 2026-10-15 15:56:47.067862

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0293c8e81454'
down_revision: Union[str, Sequence[str], None] = '3c152cef51bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payment_webhook_events",
        sa.Column("provider_refund_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payment_webhook_events", "provider_refund_id")
