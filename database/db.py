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
