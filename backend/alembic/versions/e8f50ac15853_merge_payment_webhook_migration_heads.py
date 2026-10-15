"""merge payment webhook migration heads

Revision ID: e8f50ac15853
Revises: e1f2a3b4c5d6, f2a3b4c5d6e7
Create Date: 2026-10-15 10:55:38.814729

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8f50ac15853'
down_revision: Union[str, Sequence[str], None] = ('e1f2a3b4c5d6', 'f2a3b4c5d6e7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
