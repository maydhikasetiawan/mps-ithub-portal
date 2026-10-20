import os
import psycopg2
from psycopg2.extras import RealDictCursor

_required_vars = {
    'DB_HOST': os.getenv('DB_HOST'),
    'DB_NAME': os.getenv('DB_NAME'),
    'DB_USER': os.getenv('DB_USER'),
    'DB_PASS': os.getenv('DB_PASS'),
}
_missing = [k for k, v in _required_vars.items() if not v]
if _missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(_missing)}")

DB_HOST = _required_vars['DB_HOST']
DB_NAME = _required_vars['DB_NAME']
DB_USER = _required_vars['DB_USER']
DB_PASS = _required_vars['DB_PASS']

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=5432,
        cursor_factory=RealDictCursor
    )

BRANDING_DEFAULTS = {
    'app_name': 'MPS-ITHub',
    'tagline': 'Operations Portal',
    'logo_url': '',
    'login_headline': 'Operasional IT, lebih tenang.',
    'login_text': 'Satu ruang kerja untuk aset, tiket, pemantauan layanan, dan laporan — dirancang ulang agar keputusan harian terasa lebih cepat.',
    'footer_text': '',
}

def get_branding():
    """Return the branding_settings row (id=1) as a dict merged over
    BRANDING_DEFAULTS. Never raises: on any error returns the defaults."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT app_name, tagline, logo_url, login_headline, login_text, footer_text FROM branding_settings WHERE id = 1;")
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            result = dict(BRANDING_DEFAULTS)
            for key in result:
                if row[key] is not None:
                    result[key] = row[key]
            return result
    except Exception:
        pass
    return dict(BRANDING_DEFAULTS)
