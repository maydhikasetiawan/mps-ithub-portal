"""delete_orphan_ratings_and_relationships

Revision ID: 009
Revises: 008
Create Date: 2026-10-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DELETE FROM ticket_ratings WHERE NOT EXISTS (SELECT 1 FROM tickets t WHERE t.id = ticket_ratings.ticket_id);
    """)
    op.execute("""
        DELETE FROM ticket_relationships WHERE NOT EXISTS (SELECT 1 FROM tickets t WHERE t.id = ticket_relationships.ticket_a_id) OR NOT EXISTS (SELECT 1 FROM tickets t WHERE t.id = ticket_relationships.ticket_b_id);
    """)


def downgrade() -> None:
    pass
