"""add customers and appointment ownership

Revision ID: c9d0e1f2a3b4
Revises: f8a9b0c1d2e3
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "f8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_customers_email", "customers", ["email"], unique=False)
    op.add_column("appointments", sa.Column("customer_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_appointments_customer_id", "appointments", "customers", ["customer_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_appointments_customer_id", "appointments", ["customer_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_appointments_customer_id", table_name="appointments")
    op.drop_constraint("fk_appointments_customer_id", "appointments", type_="foreignkey")
    op.drop_column("appointments", "customer_id")
    op.drop_index("ix_customers_email", table_name="customers")
    op.drop_table("customers")
