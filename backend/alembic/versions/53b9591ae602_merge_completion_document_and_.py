"""merge completion document and notification heads

Revision ID: 53b9591ae602
Revises: 386da2907626, 71756d97512d
Create Date: 2026-09-28 17:18:32.896968

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '53b9591ae602'
down_revision: Union[str, Sequence[str], None] = ('386da2907626', '71756d97512d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
