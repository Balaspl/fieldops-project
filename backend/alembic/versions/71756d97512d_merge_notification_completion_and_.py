"""merge notification completion and customer tenant heads

Revision ID: 71756d97512d
Revises: b25cd2562ab8, c7f4a82d91e3
Create Date: 2026-09-28 15:17:26.719236

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '71756d97512d'
down_revision: Union[str, Sequence[str], None] = ('b25cd2562ab8', 'c7f4a82d91e3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
