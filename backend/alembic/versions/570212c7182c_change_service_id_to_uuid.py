"""change service id to uuid

Revision ID: 570212c7182c
Revises: 16626694aa74
Create Date: 2026-09-03 16:34:10.242797

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "570212c7182c"
down_revision: Union[str, Sequence[str], None] = "16626694aa74"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.drop_table("services")

    op.create_table(
        "services",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "price",
            sa.Numeric(precision=10, scale=2),
            nullable=True,
        ),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column(
            "buffer_time_minutes",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "INACTIVE",
                name="service_status",
            ),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_table("services")

    op.create_table(
        "services",
        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "description",
            sa.String(length=1000),
            nullable=True,
        ),
        sa.Column(
            "duration_minutes",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "price",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id"),
    )  # ### end Alembic commands ###
