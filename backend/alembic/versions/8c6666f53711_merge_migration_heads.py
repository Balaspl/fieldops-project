"""merge migration heads

Revision ID: 8c6666f53711
Revises: 5358f7c95b71, fa9a3c192aa9
Create Date: 2026-09-09 15:27:30.415384

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c6666f53711'
down_revision: Union[str, Sequence[str], None] = ('5358f7c95b71', 'fa9a3c192aa9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
