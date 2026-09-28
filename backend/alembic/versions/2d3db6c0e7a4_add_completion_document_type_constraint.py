"""add completion document type constraint

Revision ID: 2d3db6c0e7a4
Revises: 219895425dee
Create Date: 2026-09-24 16:17:40.689508

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2d3db6c0e7a4'
down_revision: Union[str, Sequence[str], None] = '219895425dee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
