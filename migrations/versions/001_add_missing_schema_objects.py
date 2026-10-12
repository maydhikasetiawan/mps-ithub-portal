"""add_missing_schema_objects

Revision ID: 001
Revises: 
Create Date: 2026-10-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create departments table
    op.execute("""
        CREATE TABLE IF NOT EXISTS departments (
            id SERIAL PRIMARY KEY,
            name VARCHAR(50) UNIQUE NOT NULL
        );
    """)

    # Create monitors table
    op.execute("""
        CREATE TABLE IF NOT EXISTS monitors (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            target VARCHAR(255) NOT NULL,
            type VARCHAR(20) NOT NULL DEFAULT 'PING',
            port INT,
            status VARCHAR(20) DEFAULT 'UNKNOWN',
            latency INT DEFAULT 0,
            last_check TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Add missing columns to users table
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS department VARCHAR(50) DEFAULT 'IT';")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE;")

    # Add missing columns to tickets table
    op.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS resolution_note TEXT;")
    op.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(50);")
    op.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP;")
    op.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;")
    op.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;")
    op.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS deleted_by VARCHAR(50);")
    op.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS delete_reason TEXT;")
    op.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS department VARCHAR(50);")

    # Add missing columns to assets table
    op.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;")
    op.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;")
    op.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS deleted_by VARCHAR(50);")
    op.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS delete_reason TEXT;")


def downgrade() -> None:
    # No-op: Production database already contains these objects.
    # Dropping columns/tables would cause data loss and break the running application.
    # This migration is additive-only and not designed to be reversible.
    pass