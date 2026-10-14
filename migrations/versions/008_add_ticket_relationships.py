"""add_ticket_relationships

Revision ID: 008
Revises: 007
Create Date: 2026-10-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ticket_relationships (
            id SERIAL PRIMARY KEY,
            ticket_a_id INTEGER NOT NULL,
            ticket_b_id INTEGER NOT NULL,
            relation_type VARCHAR(20) NOT NULL,
            created_by VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)


def downgrade() -> None:
    pass
