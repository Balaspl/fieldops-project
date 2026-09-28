"""merge notification and completion document scan heads

Revision ID: b25cd2562ab8
Revises: 1b0e1c93d5ab, e02bd5217c96
Create Date: 2026-09-25 17:45:34.099688

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b25cd2562ab8'
down_revision: Union[str, Sequence[str], None] = ('1b0e1c93d5ab', 'e02bd5217c96')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
