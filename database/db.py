import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash

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

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 1. Tabel Users
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'staff',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # 2. Tabel Assets (IPAM & Inventory)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS assets (
                id SERIAL PRIMARY KEY,
                asset_tag VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                category VARCHAR(50) NOT NULL,
                ip_address VARCHAR(45),
                mac_address VARCHAR(45),
                status VARCHAR(20) DEFAULT 'Active',
                location VARCHAR(100),
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by VARCHAR(50)
            );
        ''')

        # 3. Tabel Tickets
        cur.execute('''
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # 4. Tabel Service Monitors
        cur.execute('''
            CREATE TABLE IF NOT EXISTS service_monitors (
                id SERIAL PRIMARY KEY,
                service_name VARCHAR(100) NOT NULL,
                target_url VARCHAR(255) NOT NULL,
                last_status VARCHAR(20) DEFAULT 'Unknown',
                response_time_ms INT DEFAULT 0,
                last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # 5. Tabel Ticket Categories (Modular)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ticket_categories (
                id SERIAL PRIMARY KEY,
                name VARCHAR(50) UNIQUE NOT NULL
            );
        ''')

        # 6. Tabel Ticket Activities
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ticket_activities (
                id SERIAL PRIMARY KEY,
                ticket_id INT NOT NULL,
                actor VARCHAR(50),
                type VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # 7. Tabel Ticket Attachments
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ticket_attachments (
                id SERIAL PRIMARY KEY,
                ticket_id INT NOT NULL,
                stored_filename VARCHAR(255) NOT NULL,
                original_filename VARCHAR(255) NOT NULL,
                size_bytes INT NOT NULL,
                mime_type VARCHAR(100),
                uploader VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # 8. Tabel Knowledge Base Articles
        cur.execute('''
            CREATE TABLE IF NOT EXISTS kb_articles (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                category VARCHAR(100) NOT NULL,
                content TEXT NOT NULL,
                tags VARCHAR(255),
                status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
                author VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # 9. Tabel Ticket Ratings (CSAT)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ticket_ratings (
                id SERIAL PRIMARY KEY,
                ticket_id INT NOT NULL UNIQUE,
                rating INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
                comment TEXT,
                rater VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # 10. Tabel Canned Responses (Templates)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS canned_responses (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                category VARCHAR(100) NOT NULL DEFAULT 'Umum',
                author VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # 11. Tabel Ticket Relationships
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ticket_relationships (
                id SERIAL PRIMARY KEY,
                ticket_a_id INTEGER NOT NULL,
                ticket_b_id INTEGER NOT NULL,
                relation_type VARCHAR(20) NOT NULL,
                created_by VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # Insert Default Categories Jika Belum Ada
        default_categories = ['Hardware', 'Network', 'Software', 'Server', 'Request']
        for cat in default_categories:
            cur.execute("INSERT INTO ticket_categories (name) VALUES (%s) ON CONFLICT (name) DO NOTHING;", (cat,))

        # Default Accounts
        cur.execute("SELECT * FROM users WHERE username = 'admin';")
        if not cur.fetchone():
            admin_pass = generate_password_hash('AdminPass123!')
            cur.execute(
                "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s);",
                ('admin', 'admin@mpshub.my.id', admin_pass, 'admin')
            )

        cur.execute("SELECT * FROM users WHERE username = 'guest';")
        if not cur.fetchone():
            guest_pass = generate_password_hash('GuestPass123!')
            cur.execute(
                "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s);",
                ('guest', 'guest@mpshub.my.id', guest_pass, 'guest')
            )

        conn.commit()
        cur.close()
        conn.close()
        print("Database & Default Users initialized successfully.")
    except Exception as e:
        print(f"Error initializing DB: {e}")
