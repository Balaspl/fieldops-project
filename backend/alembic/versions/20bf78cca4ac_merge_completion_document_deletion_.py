"""merge completion document deletion migration

Revision ID: 20bf78cca4ac
Revises: 9853b2f0bcd3, a42f1c8d7b91
Create Date: 2026-09-30 13:27:44.782593

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20bf78cca4ac'
down_revision: Union[str, Sequence[str], None] = ('9853b2f0bcd3', 'a42f1c8d7b91')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
