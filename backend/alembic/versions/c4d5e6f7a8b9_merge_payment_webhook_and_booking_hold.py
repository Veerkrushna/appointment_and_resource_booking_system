"""merge payment webhook and booking hold branches

Revision ID: c4d5e6f7a8b9
Revises: a1b2c3d4e5f7, e8f9a0b1c2d3
"""

from collections.abc import Sequence

revision: str = "c4d5e6f7a8b9"
down_revision: str | Sequence[str] | None = (
    "a1b2c3d4e5f7",
    "e8f9a0b1c2d3",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
