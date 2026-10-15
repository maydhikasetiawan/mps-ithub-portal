"""add_asset_activities

Revision ID: 013
Revises: 012
Create Date: 2026-10-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '013'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS asset_activities (
            id SERIAL PRIMARY KEY,
            asset_id INT NOT NULL,
            actor VARCHAR(50),
            action VARCHAR(20) NOT NULL,
            field_name VARCHAR(50),
            old_value TEXT,
            new_value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)


def downgrade() -> None:
    pass
