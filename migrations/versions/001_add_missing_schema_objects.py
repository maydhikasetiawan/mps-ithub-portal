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
    # Base tables (added Batch 1b): Alembic is the single schema authority.
    # These CREATEs run BEFORE the ALTERs below. All IF NOT EXISTS, so they
    # are no-ops on databases that already have these tables (e.g. production,
    # which never re-runs 001). Phantom tables from legacy schema are
    # intentionally excluded.
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'staff',
            department VARCHAR(50) DEFAULT 'IT',
            must_change_password BOOLEAN DEFAULT FALSE,
            is_deleted BOOLEAN DEFAULT FALSE,
            deleted_at TIMESTAMP,
            deleted_by VARCHAR(50),
            delete_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_is_deleted ON users (is_deleted);")
    op.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id SERIAL PRIMARY KEY,
            ticket_code VARCHAR(20) UNIQUE NOT NULL,
            title VARCHAR(150) NOT NULL,
            category VARCHAR(50) NOT NULL,
            priority VARCHAR(20) DEFAULT 'Medium',
            status VARCHAR(20) DEFAULT 'Open',
            description TEXT,
            created_by VARCHAR(50),
            assigned_to VARCHAR(50),
            resolution_note TEXT,
            resolved_by VARCHAR(50),
            resolved_at TIMESTAMP,
            is_deleted BOOLEAN DEFAULT FALSE,
            deleted_at TIMESTAMP,
            deleted_by VARCHAR(50),
            delete_reason TEXT,
            department VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            id SERIAL PRIMARY KEY,
            asset_tag VARCHAR(50) UNIQUE NOT NULL,
            serial_number VARCHAR(100),
            name VARCHAR(100) NOT NULL,
            category VARCHAR(50) NOT NULL,
            ip_address VARCHAR(45),
            mac_address VARCHAR(45),
            status VARCHAR(20) DEFAULT 'Active',
            location VARCHAR(100),
            notes TEXT,
            assigned_to VARCHAR(50),
            purchase_date DATE,
            warranty_expiry DATE,
            no_warranty BOOLEAN DEFAULT FALSE,
            is_deleted BOOLEAN DEFAULT FALSE,
            deleted_at TIMESTAMP,
            deleted_by VARCHAR(50),
            delete_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by VARCHAR(50)
        );
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS ticket_categories (
            id SERIAL PRIMARY KEY,
            name VARCHAR(50) UNIQUE NOT NULL
        );
    """)

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