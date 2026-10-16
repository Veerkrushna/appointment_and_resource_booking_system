"""add payment refunds

Revision ID: 3c152cef51bb
Revises: e8f50ac15853
Create Date: 2026-10-15 15:36:08.152710

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c152cef51bb"
down_revision: str | Sequence[str] | None = "e8f50ac15853"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE payment_refund_status AS ENUM "
        "('PENDING', 'PROCESSING', 'PROCESSED', 'FAILED')"
    )
    op.create_table(
        "payment_refunds",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("payment_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING",
                "PROCESSING",
                "PROCESSED",
                "FAILED",
                name="payment_refund_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("razorpay_refund_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name="fk_payment_refunds_payment_id_payments",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_payment_refunds_idempotency_key",
        ),
        sa.UniqueConstraint(
            "razorpay_refund_id",
            name="uq_payment_refunds_razorpay_refund_id",
        ),
    )
    op.create_index("ix_payment_refunds_payment_id", "payment_refunds", ["payment_id"])
    op.create_index("ix_payment_refunds_status", "payment_refunds", ["status"])


def downgrade() -> None:
    op.drop_index("ix_payment_refunds_status", table_name="payment_refunds")
    op.drop_index("ix_payment_refunds_payment_id", table_name="payment_refunds")
    op.drop_table("payment_refunds")
    op.execute("DROP TYPE payment_refund_status")
