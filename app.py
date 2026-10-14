import os
from flask import Flask
from database.db import init_db
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.assets import assets_bp
from routes.tickets import tickets_bp
from routes.reports import reports_bp
from routes.users import users_bp # 1. Import Blueprint Users
from routes.knowledge_base import knowledge_base_bp
from flask import session, redirect, url_for, request, flash
from routes.uptime import uptime_bp

app = Flask(__name__)
secret_key = os.getenv('SECRET_KEY')
if not secret_key:
    raise RuntimeError("Missing required environment variable: SECRET_KEY")
app.secret_key = secret_key

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(assets_bp)
app.register_blueprint(tickets_bp)
app.register_blueprint(knowledge_base_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(users_bp) # 2. Register Blueprint Users

@app.before_request
def ensure_db_initialized():
    if not getattr(app, '_got_first_request', False):
        init_db()
        app._got_first_request = True

@app.before_request
def check_mandatory_password_change():
    if session.get('user_id'):
        # Jalankan pengecekan jika user wajib ganti password
        if session.get('must_change_password') and request.endpoint not in ['users.change_password', 'auth.logout', 'static']:
            flash("Demi keamanan, Anda diwajibkan mengganti password setelah di-reset oleh Admin.", "warning")
            return redirect(url_for('users.change_password'))

app.register_blueprint(uptime_bp)

@app.route('/health')
def health():
    return {"status": "healthy"}, 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
