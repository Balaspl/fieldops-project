"""merge MFA and completion checklist migrations

Revision ID: 621b2ee94385
Revises: 5b9a26aea696, 85b9e52b03d9
Create Date: 2026-09-16 17:47:58.850435

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '621b2ee94385'
down_revision: Union[str, Sequence[str], None] = ('5b9a26aea696', '85b9e52b03d9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
