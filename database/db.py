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


def get_nav_counts():
    """get_nav_counts: Sidebar badge counts: open tickets + active assets (same
    definitions as the dashboard stat cards). Never raises:
    returns {} on any error."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS count FROM tickets WHERE status IN ('Open', 'In Progress') AND is_deleted = FALSE;")
        tickets = cur.fetchone()['count']
        cur.execute("SELECT COUNT(*) AS count FROM assets WHERE is_deleted = FALSE;")
        assets = cur.fetchone()['count']
        cur.close()
        conn.close()
        return {'tickets': tickets, 'assets': assets}
    except Exception:
        return {}


def get_hub_setting(key):
    """Return stored value for key, or None when absent or decrypt fails."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT value, is_secret FROM hub_settings WHERE key = %s;", (key,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        if row.get('is_secret'):
            from database.crypto import decrypt_value
            return decrypt_value(row['value'])
        return row['value']
    except Exception:
        return None



def hub_setting_decrypt_failed(key):
    """Return True only when a secret row exists in hub_settings but decrypt failed."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT value, is_secret FROM hub_settings WHERE key = %s;", (key,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row or not row.get('is_secret'):
            return False
        from database.crypto import decrypt_value
        return decrypt_value(row['value']) is None
    except Exception:
        return False



def set_hub_setting(key, value, is_secret=False):
    """Upsert a key into hub_settings.
    If is_secret is True, encrypts value. Raises ValueError if encryption fails or no cipher.
    """
    stored_value = value
    if is_secret:
        from database.crypto import encrypt_value
        encrypted = encrypt_value(value)
        if encrypted is None:
            raise ValueError("Encryption unavailable or invalid key")
        stored_value = encrypted

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO hub_settings (key, value, is_secret, updated_at)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (key) DO UPDATE SET
            value = EXCLUDED.value,
            is_secret = EXCLUDED.is_secret,
            updated_at = CURRENT_TIMESTAMP;
    """, (key, stored_value, is_secret))
    conn.commit()
    cur.close()
    conn.close()



def delete_hub_setting(key):
    """Delete a key from hub_settings. Return True on success, False on error."""
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM hub_settings WHERE key = %s;", (key,))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()
        return False
