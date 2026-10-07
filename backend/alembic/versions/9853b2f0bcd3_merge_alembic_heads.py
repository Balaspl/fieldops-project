"""merge alembic heads

Revision ID: 9853b2f0bcd3
Revises: 53b9591ae602, 836d2d261262
Create Date: 2026-09-30 11:11:15.389911

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9853b2f0bcd3'
down_revision: Union[str, Sequence[str], None] = ('53b9591ae602', '836d2d261262')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
