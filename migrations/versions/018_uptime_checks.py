"""uptime_checks

Revision ID: 018
Revises: 017
Create Date: 2026-10-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '018'
down_revision: Union[str, None] = '017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS uptime_checks (
            id SERIAL PRIMARY KEY,
            monitor_id INT NOT NULL,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(10) NOT NULL,
            latency INT NOT NULL
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_uptime_checks_monitor_time
        ON uptime_checks (monitor_id, checked_at);
    """)


def downgrade() -> None:
    pass
