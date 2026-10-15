"""add_asset_warranty_dates

Revision ID: 011
Revises: 010
Create Date: 2026-10-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '011'
down_revision: Union[str, None] = '010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS purchase_date DATE;")
    op.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS warranty_expiry DATE;")


def downgrade() -> None:
    pass
