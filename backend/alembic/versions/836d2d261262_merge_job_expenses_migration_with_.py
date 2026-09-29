"""merge job expenses migration with current migrations

Revision ID: 836d2d261262
Revises: c7a31f4e8d20, 71756d97512d
Create Date: 2026-09-28 20:53:07.941342

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '836d2d261262'
down_revision: Union[str, Sequence[str], None] = ('c7a31f4e8d20', '71756d97512d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
