"""merge current migration heads

Revision ID: 628e63a9b7e8
Revises: 555195a910ad, 0f4a7b3c2d11
Create Date: 2026-10-06 16:02:12.707886

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '628e63a9b7e8'
down_revision: Union[str, Sequence[str], None] = ('555195a910ad', '0f4a7b3c2d11')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
