"""merge customer confirmations and support requests heads

Revision ID: 555195a910ad
Revises: c18d6037b2e9, c4d7e19a2b31
Create Date: 2026-10-06 13:38:29.459751

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '555195a910ad'
down_revision: Union[str, Sequence[str], None] = ('c18d6037b2e9', 'c4d7e19a2b31')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
