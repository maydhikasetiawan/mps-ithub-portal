"""telegram_settings

Revision ID: 017
Revises: 016
Create Date: 2026-10-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '017'
down_revision: Union[str, None] = '016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS telegram_settings (
            id INT PRIMARY KEY,
            bot_token TEXT NOT NULL DEFAULT '',
            chat_id VARCHAR(64) NOT NULL DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    op.execute("""
        INSERT INTO telegram_settings (id) VALUES (1)
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    pass
