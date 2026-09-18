"""merge trusted devices and MFA heads

Revision ID: 0e98d23f998c
Revises: 22c3907b165a, 621b2ee94385
Create Date: 2026-09-18 23:09:46.966602

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0e98d23f998c'
down_revision: Union[str, Sequence[str], None] = ('22c3907b165a', '621b2ee94385')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
