"""uptime_alerts

Revision ID: 016
Revises: 015
Create Date: 2026-10-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '016'
down_revision: Union[str, None] = '015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS uptime_alerts (
            id SERIAL PRIMARY KEY,
            monitor_id INT NOT NULL,
            alert_type VARCHAR(20) NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    op.execute("""
        ALTER TABLE monitors
        ADD COLUMN IF NOT EXISTS consecutive_failures INT NOT NULL DEFAULT 0;
    """)


def downgrade() -> None:
    pass
