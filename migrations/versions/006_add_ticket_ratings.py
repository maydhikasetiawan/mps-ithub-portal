"""add_ticket_ratings

Revision ID: 006
Revises: 005
Create Date: 2026-10-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ticket_ratings (
            id SERIAL PRIMARY KEY,
            ticket_id INT NOT NULL UNIQUE,
            rating INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
            comment TEXT,
            rater VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)


def downgrade() -> None:
    pass
