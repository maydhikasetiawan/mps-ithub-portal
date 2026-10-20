from flask import Blueprint, render_template, request, redirect, url_for, flash
from routes.auth import login_required, roles_required
from database.db import get_db_connection, get_branding

branding_bp = Blueprint('branding', __name__)


@branding_bp.route('/settings/branding', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def branding_settings():
    if request.method == 'POST':
        app_name = request.form.get('app_name', '').strip()
        tagline = request.form.get('tagline', '').strip()
        logo_url = request.form.get('logo_url', '').strip()
        login_headline = request.form.get('login_headline', '').strip()
        login_text = request.form.get('login_text', '').strip()
        footer_text = request.form.get('footer_text', '').strip()

        current = get_branding()
        if not app_name:
            app_name = current['app_name']

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE branding_settings
            SET app_name = %s, tagline = %s, logo_url = %s,
                login_headline = %s, login_text = %s, footer_text = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1;
        """, (app_name, tagline, logo_url, login_headline, login_text, footer_text))
        conn.commit()
        cur.close()
        conn.close()

        flash('Pengaturan branding disimpan.', 'success')
        return redirect(url_for('branding.branding_settings'))

    branding = get_branding()
    return render_template('branding/settings.html', branding=branding, active_page='users')
