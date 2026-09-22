"""merge completion documents migration heads

Revision ID: 1a02f91166b3
Revises: 0e98d23f998c, ad0f8cad1a9a
Create Date: 2026-09-19 13:04:24.508640

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a02f91166b3'
down_revision: Union[str, Sequence[str], None] = ('0e98d23f998c', 'ad0f8cad1a9a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
