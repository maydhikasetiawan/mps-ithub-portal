import os
import threading
import time
import secrets
from datetime import datetime, timedelta, timezone
from flask import Flask
from flask.sessions import SecureCookieSessionInterface
from werkzeug.middleware.proxy_fix import ProxyFix
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.assets import assets_bp
from routes.tickets import tickets_bp
from routes.reports import reports_bp
from routes.users import users_bp # 1. Import Blueprint Users
from routes.knowledge_base import knowledge_base_bp
from routes.api import api_bp
from routes.branding import branding_bp
from routes.setup import setup_bp
from database.db import get_branding, get_nav_counts
from flask import session, redirect, url_for, request, flash, abort
from routes.uptime import uptime_bp, start_uptime_scheduler, send_telegram_alert

app = Flask(__name__)
# Trust X-Forwarded-* headers from the single Nginx reverse
# proxy in front of the app (exactly 1 hop — do NOT increase
# these values). This makes url_for(_external=True) generate
# https:// URLs matching what browsers actually use.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
secret_key = os.getenv('SECRET_KEY')
if not secret_key:
    raise RuntimeError("Missing required environment variable: SECRET_KEY")
app.secret_key = secret_key

# Idle session timeout: cookie expires after 30 minutes with no requests.
# SESSION_REFRESH_EACH_REQUEST=True (Flask default, made explicit) means
# every request refreshes the expiry, so the 30 minutes count idle time.
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Remember-me: a session flagged 'remember_me' at login (the user
# checked "Ingat saya") gets a 30-day idle lifetime; every other
# session keeps the 30-minute lifetime configured above.
class _RememberMeSessionInterface(SecureCookieSessionInterface):
    def get_expiration_time(self, app, session):
        if session.get('remember_me'):
            return datetime.now(timezone.utc) + timedelta(days=30)
        return super().get_expiration_time(app, session)


app.session_interface = _RememberMeSessionInterface()

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(assets_bp)
app.register_blueprint(tickets_bp)
app.register_blueprint(knowledge_base_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(users_bp) # 2. Register Blueprint Users
app.register_blueprint(api_bp)
app.register_blueprint(branding_bp)
app.register_blueprint(setup_bp)

@app.context_processor
def inject_branding():
    return {'branding': get_branding(), 'nav_counts': get_nav_counts()}

_scheduler_lock = threading.Lock()

@app.before_request
def ensure_scheduler_started():
    if getattr(app, '_scheduler_started', False):
        return
    with _scheduler_lock:
        if not getattr(app, '_scheduler_started', False):
            start_uptime_scheduler()
            app._scheduler_started = True

@app.before_request
def check_mandatory_password_change():
    if session.get('user_id'):
        # Jalankan pengecekan jika user wajib ganti password
        if session.get('must_change_password') and request.endpoint not in ['users.change_password', 'auth.logout', 'static']:
            flash("Demi keamanan, Anda diwajibkan mengganti password setelah di-reset oleh Admin.", "warning")
            return redirect(url_for('users.change_password'))

# --- CSRF protection (session token, hand-rolled) -------------------
# Every HTML form POST must carry the per-session token rendered
# into the form as a hidden field. The token is generated lazily
# the first time a page renders it (or a POST is checked).
def _csrf_token():
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_csrf_token'] = token
    return token

@app.context_processor
def inject_csrf_token():
    return {'csrf_token': _csrf_token()}

@app.before_request
def csrf_protect():
    if request.method != 'POST':
        return None
    if request.endpoint is None:
        return None  # let Flask answer 404/405 itself
    if request.blueprint == 'api_v1':
        return None  # API-key header auth, not cookie forms
    sent = request.form.get('_csrf_token')
    expected = session.get('_csrf_token')
    if not expected or not sent or not secrets.compare_digest(expected, sent):
        abort(403)
    return None

app.register_blueprint(uptime_bp)

@app.route('/health')
def health():
    return {"status": "healthy"}, 200


# --- Fase 9.2: Telegram alert for HTTP 500 errors ---------------------------
# Reuses send_telegram_alert from routes.uptime (reads telegram_settings,
# never raises). Rate limit: at most 1 alert per error signature
# (exception class + path) per 300 seconds. Gunicorn runs 1 worker,
# so this in-memory window is exact; the lock covers its 4 threads.
_error_alert_lock = threading.Lock()
_error_alert_last = {}
_ERROR_ALERT_WINDOW = 300


@app.errorhandler(500)
def handle_internal_error(error):
    try:
        original = getattr(error, 'original_exception', None)
        exc = original if original is not None else error
        signature = f"{type(exc).__name__}:{request.path}"
        now = time.monotonic()
        with _error_alert_lock:
            due = now - _error_alert_last.get(signature, -_ERROR_ALERT_WINDOW) >= _ERROR_ALERT_WINDOW
            if due:
                _error_alert_last[signature] = now
        if due:
            text = (
                "🚨 Error 500 — MPS-ITHub Portal\n"
                f"{request.method} {request.path}\n"
                f"{type(exc).__name__}: {exc}"
            )[:500]
            send_telegram_alert(text)
    except Exception:
        app.logger.exception("Failed to send HTTP 500 Telegram alert")
    return error


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
