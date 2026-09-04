"""create appointment cancellations table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "appointment_cancellations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("appointment_id", sa.UUID(), nullable=False),
        sa.Column("cancelled_by", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "refund_status",
            sa.Enum(
                "PENDING",
                "REFUNDED",
                "NOT_ELIGIBLE",
                name="refund_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "cancelled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"], ["appointments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_appointment_cancellations_appointment_id",
        "appointment_cancellations",
        ["appointment_id"],
    )
    op.create_index(
        "ix_appointment_cancellations_cancelled_at",
        "appointment_cancellations",
        ["cancelled_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_appointment_cancellations_cancelled_at",
        table_name="appointment_cancellations",
    )
    op.drop_index(
        "ix_appointment_cancellations_appointment_id",
        table_name="appointment_cancellations",
    )
    op.drop_table("appointment_cancellations")
    sa.Enum(name="refund_status").drop(op.get_bind(), checkfirst=True)