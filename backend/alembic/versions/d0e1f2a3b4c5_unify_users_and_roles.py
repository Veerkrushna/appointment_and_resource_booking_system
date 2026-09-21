"""unify customers into role-based users

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: str | Sequence[str] | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE customers RENAME TO users")
    op.execute("CREATE TYPE user_role AS ENUM ('CUSTOMER', 'PROVIDER', 'ADMIN')")
    op.add_column("users", sa.Column("role", postgresql.ENUM("CUSTOMER", "PROVIDER", "ADMIN", name="user_role", create_type=False), nullable=True))
    op.add_column("users", sa.Column("created_by", sa.UUID(), nullable=True))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=True))
    op.execute("UPDATE users SET role = 'CUSTOMER', is_active = TRUE")
    op.alter_column("users", "role", nullable=False)
    op.alter_column("users", "is_active", nullable=False)
    op.create_foreign_key("fk_users_created_by", "users", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.alter_column("appointments", "customer_id", existing_type=sa.UUID(), nullable=True)
    op.drop_constraint("fk_appointments_customer_id", "appointments", type_="foreignkey")
    op.create_foreign_key("fk_appointments_customer_id", "appointments", "users", ["customer_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_appointments_customer_id", "appointments", type_="foreignkey")
    op.create_foreign_key("fk_appointments_customer_id", "appointments", "customers", ["customer_id"], ["id"], ondelete="SET NULL")
    op.drop_constraint("fk_users_created_by", "users", type_="foreignkey")
    op.drop_column("users", "is_active")
    op.drop_column("users", "created_by")
    op.drop_column("users", "role")
    op.execute("DROP TYPE user_role")
    op.execute("ALTER TABLE users RENAME TO customers")
