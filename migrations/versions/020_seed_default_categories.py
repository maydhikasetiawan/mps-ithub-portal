"""seed_default_categories

Revision ID: 020
Revises: 019
Create Date: 2026-10-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '020'
down_revision: Union[str, None] = '019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Seed the default ticket categories. Idempotent: ON CONFLICT DO NOTHING,
    # so re-running (or running on production, where they already exist) is a no-op.
    # User accounts are intentionally NOT seeded here (no hardcoded passwords).
    op.execute("""
        INSERT INTO ticket_categories (name) VALUES
            ('Hardware'), ('Network'), ('Software'), ('Server'), ('Request')
        ON CONFLICT (name) DO NOTHING;
    """)


def downgrade() -> None:
    pass
