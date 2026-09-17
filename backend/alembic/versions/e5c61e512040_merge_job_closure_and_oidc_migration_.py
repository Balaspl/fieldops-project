"""merge job closure and oidc migration heads

Revision ID: e5c61e512040
Revises: 37e853af22ad, 57218f56acf
Create Date: 2026-09-15 11:19:30.028398

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5c61e512040'
down_revision: Union[str, Sequence[str], None] = ('37e853af22ad', '57218f56acf')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
