"""user_soft_delete

Revision ID: 019
Revises: 018
Create Date: 2026-10-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '019'
down_revision: Union[str, None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS deleted_by VARCHAR(50),
            ADD COLUMN IF NOT EXISTS delete_reason TEXT;
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_is_deleted ON users (is_deleted);")


def downgrade() -> None:
    pass
