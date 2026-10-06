"""merge_heads

Revision ID: e4971b017415
Revises: c223c51abc8a, f1a2b3c4d5e6
Create Date: 2026-10-06 15:27:42.915480

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4971b017415'
down_revision: Union[str, Sequence[str], None] = ('c223c51abc8a', 'f1a2b3c4d5e6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
