from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash
from psycopg2 import IntegrityError
from database.db import get_db_connection

setup_bp = Blueprint('setup', __name__)


def _setup_allowed():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE is_deleted = FALSE;")
        res = cur.fetchone()
        cur.close()
        conn.close()
        if not res:
            return False
        count = res['count'] if isinstance(res, dict) else res[0]
        return count == 0
    except Exception:
        return False


@setup_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    if not _setup_allowed():
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        app_name = request.form.get('app_name', '').strip()
        tagline = request.form.get('tagline', '').strip()
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()

        if not all([app_name, tagline, username, email, password, password_confirm]):
            flash("Semua field wajib diisi.", "danger")
            return render_template('setup.html')

        if len(username) > 50:
            flash("Username maksimal 50 karakter.", "danger")
            return render_template('setup.html')

        if len(email) > 100:
            flash("Email maksimal 100 karakter.", "danger")
            return render_template('setup.html')

        if password != password_confirm:
            flash("Konfirmasi password tidak cocok.", "danger")
            return render_template('setup.html')

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE branding_settings
                SET app_name = %s, tagline = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1;
            """, (app_name, tagline))

            password_hash = generate_password_hash(password)
            cur.execute("""
                INSERT INTO users (username, email, password_hash, role)
                VALUES (%s, %s, %s, 'admin');
            """, (username, email, password_hash))

            conn.commit()
            cur.close()
            conn.close()
            flash("Setup berhasil! Silakan login dengan akun administrator.", "success")
            return redirect(url_for('auth.login'))
        except IntegrityError:
            conn.rollback()
            cur.close()
            conn.close()
            flash("Username atau email sudah terdaftar.", "danger")
            return render_template('setup.html')
        except Exception:
            conn.rollback()
            cur.close()
            conn.close()
            flash("Terjadi kesalahan saat memproses setup.", "danger")
            return render_template('setup.html')

    return render_template('setup.html')
