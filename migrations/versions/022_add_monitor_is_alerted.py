"""add_monitor_is_alerted

Revision ID: 022
Revises: 021
Create Date: 2026-10-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '022'
down_revision: Union[str, None] = '021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE monitors
        ADD COLUMN IF NOT EXISTS is_alerted BOOLEAN NOT NULL DEFAULT FALSE;
    """)


def downgrade() -> None:
    pass
