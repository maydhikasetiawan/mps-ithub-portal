from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from functools import wraps
from database.db import get_db_connection
import time
import logging

auth_bp = Blueprint('auth', __name__)

_login_attempts = {}

def _get_client_ip():
    real_ip = request.headers.get('X-Real-IP', '').strip()
    if real_ip:
        return real_ip
    return request.remote_addr or 'unknown'

def _check_rate_limit(ip, username):
    key = f"{ip}:{username}"
    now = time.time()
    window_start = now - 900
    attempts = _login_attempts.get(key, [])
    attempts = [t for t in attempts if t > window_start]
    if not attempts:
        _login_attempts.pop(key, None)
        return True, 0
    if len(attempts) >= 5:
        oldest = attempts[0]
        lockout_remaining = int(oldest + 900 - now)
        if lockout_remaining > 0:
            return False, lockout_remaining
    return True, 0

def _record_failed_attempt(ip, username):
    key = f"{ip}:{username}"
    now = time.time()
    window_start = now - 900
    attempts = _login_attempts.get(key, [])
    attempts = [t for t in attempts if t > window_start]
    attempts.append(now)
    _login_attempts[key] = attempts
    logging.warning(f"Failed login attempt: ip={ip} username={username}")

def _reset_attempts(ip, username):
    key = f"{ip}:{username}"
    if key in _login_attempts:
        del _login_attempts[key]

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# Decorator Pembantu Proteksi Role
def roles_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth.login'))

            user_role = session.get('role', 'guest')
            if user_role not in allowed_roles:
                flash("Akses ditolak! Anda tidak memiliki izin untuk mengakses halaman tersebut.", "danger")
                return redirect(url_for('dashboard.index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard.index'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        ip = _get_client_ip()
        allowed, lockout_remaining = _check_rate_limit(ip, username)
        if not allowed:
            error = f"Terlalu banyak percobaan gagal. Coba lagi dalam {lockout_remaining} detik."
            logging.warning(f"Login lockout triggered: ip={ip} username={username} lockout_remaining={lockout_remaining}")
            return render_template('login.html', error=error), 429

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE username = %s;", (username,))
            user = cur.fetchone()
            cur.close()
            conn.close()

            if user and check_password_hash(user['password_hash'], password):
                _reset_attempts(ip, username)
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                session['department'] = user.get('department', 'IT')
                session['must_change_password'] = user.get('must_change_password', False)

                return redirect(url_for('dashboard.index'))
            else:
                _record_failed_attempt(ip, username)
                error = "Username atau password salah!"
        except Exception as e:
            error = f"Database error: {e}"

    return render_template('login.html', error=error)

@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
