"""branding_settings

Revision ID: 024
Revises: 023
Create Date: 2026-10-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '024'
down_revision: Union[str, None] = '023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS branding_settings (
            id INT PRIMARY KEY,
            app_name VARCHAR(100) NOT NULL DEFAULT 'MPS-ITHub',
            tagline VARCHAR(200) NOT NULL DEFAULT 'Operations Portal',
            logo_url TEXT NOT NULL DEFAULT '',
            login_headline VARCHAR(200) NOT NULL DEFAULT 'Operasional IT, lebih tenang.',
            login_text TEXT NOT NULL DEFAULT 'Satu ruang kerja untuk aset, tiket, pemantauan layanan, dan laporan — dirancang ulang agar keputusan harian terasa lebih cepat.',
            footer_text VARCHAR(300) NOT NULL DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    op.execute("""
        INSERT INTO branding_settings (id) VALUES (1)
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    pass
