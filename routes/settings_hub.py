import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from routes.auth import login_required, roles_required
from routes.tickets import get_sla_targets
import database.db
from database.db import (
    get_hub_setting,
    set_hub_setting,
    delete_hub_setting,
    hub_setting_decrypt_failed,
)

settings_hub_bp = Blueprint('settings_hub', __name__)


@settings_hub_bp.route('/settings', methods=['GET'])
@login_required
@roles_required('admin')
def hub():
    sla_keys = [
        'sla_critical_response', 'sla_critical_resolution',
        'sla_high_response', 'sla_high_resolution',
        'sla_medium_response', 'sla_medium_resolution',
        'sla_low_response', 'sla_low_resolution',
    ]
    sla_in_db = any(get_hub_setting(k) is not None for k in sla_keys)
    sla_source = 'database' if sla_in_db else 'default'
    sla_targets = get_sla_targets()

    # Webhook
    webhook_decrypt_failed = hub_setting_decrypt_failed('webhook_url')
    db_webhook = get_hub_setting('webhook_url')
    if webhook_decrypt_failed:
        webhook_source = 'database'
        webhook_stored = True
    elif db_webhook is not None:
        webhook_source = 'database'
        webhook_stored = bool(db_webhook.strip())
    elif os.environ.get('WEBHOOK_URL'):
        webhook_source = 'environment'
        webhook_stored = True
    else:
        webhook_source = 'default'
        webhook_stored = False

    # Interval
    db_interval = get_hub_setting('uptime_interval_seconds')
    if db_interval is not None:
        try:
            interval_value = int(db_interval)
            interval_source = 'database'
        except (ValueError, TypeError):
            interval_value = 300
            interval_source = 'default'
    elif os.environ.get('UPTIME_CHECK_INTERVAL'):
        try:
            interval_value = int(os.environ.get('UPTIME_CHECK_INTERVAL'))
            interval_source = 'environment'
        except (ValueError, TypeError):
            interval_value = 300
            interval_source = 'default'
    else:
        interval_value = 300
        interval_source = 'default'

    # API Key
    api_key_decrypt_failed = hub_setting_decrypt_failed('api_key')
    db_api_key = get_hub_setting('api_key')
    if api_key_decrypt_failed:
        api_key_source = 'database'
        api_key_stored = True
    elif db_api_key is not None:
        api_key_source = 'database'
        api_key_stored = bool(db_api_key.strip())
    elif os.environ.get('API_KEY'):
        api_key_source = 'environment'
        api_key_stored = True
    else:
        api_key_source = 'default'
        api_key_stored = False

    return render_template(
        'settings/hub.html',
        active_page='settings',
        sla_targets=sla_targets,
        sla_source=sla_source,
        webhook_source=webhook_source,
        webhook_stored=webhook_stored,
        webhook_decrypt_failed=webhook_decrypt_failed,
        interval_value=interval_value,
        interval_source=interval_source,
        api_key_source=api_key_source,
        api_key_stored=api_key_stored,
        api_key_decrypt_failed=api_key_decrypt_failed,
    )


@settings_hub_bp.route('/settings/sla', methods=['POST'])
@login_required
@roles_required('admin')
def update_sla():
    priorities = [
        ('sla_critical_response', 'sla_critical_resolution'),
        ('sla_high_response', 'sla_high_resolution'),
        ('sla_medium_response', 'sla_medium_resolution'),
        ('sla_low_response', 'sla_low_resolution'),
    ]
    parsed = {}
    valid = True
    for resp_key, res_key in priorities:
        resp_raw = request.form.get(resp_key, '').strip()
        res_raw = request.form.get(res_key, '').strip()
        try:
            resp_val = int(resp_raw)
            res_val = int(res_raw)
            if resp_val < 1 or res_val < 1 or resp_val > res_val:
                valid = False
                break
            parsed[resp_key] = resp_val
            parsed[res_key] = res_val
        except (ValueError, TypeError):
            valid = False
            break

    if not valid:
        flash("Target SLA dibatalkan. Semua nilai harus berupa bilangan bulat >= 1 dan waktu respon <= waktu resolusi.", "danger")
        return redirect(url_for('settings_hub.hub'))

    conn = database.db.get_db_connection()
    cur = conn.cursor()
    try:
        for k, v in parsed.items():
            cur.execute("""
                INSERT INTO hub_settings (key, value, is_secret, updated_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    is_secret = EXCLUDED.is_secret,
                    updated_at = CURRENT_TIMESTAMP;
            """, (k, str(v), False))
        conn.commit()
        flash("Target SLA berhasil disimpan.", "success")
    except Exception:
        conn.rollback()
        flash("Gagal menyimpan target SLA ke database.", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('settings_hub.hub'))


@settings_hub_bp.route('/settings/webhook', methods=['POST'])
@login_required
@roles_required('admin')
def update_webhook():
    webhook_url = request.form.get('webhook_url', '').strip()
    if not webhook_url:
        set_hub_setting('webhook_url', '', is_secret=False)
        flash("Pengaturan Webhook berhasil disimpan.", "success")
        return redirect(url_for('settings_hub.hub'))

    if not (webhook_url.startswith('http://') or webhook_url.startswith('https://')):
        flash("URL Webhook harus diawali http:// atau https://.", "danger")
        return redirect(url_for('settings_hub.hub'))

    try:
        set_hub_setting('webhook_url', webhook_url, is_secret=True)
    except ValueError:
        flash("Kunci enkripsi SETTINGS_ENCRYPTION_KEY belum dikonfigurasi.", "danger")
        return redirect(url_for('settings_hub.hub'))

    flash("Pengaturan Webhook berhasil disimpan.", "success")
    return redirect(url_for('settings_hub.hub'))


@settings_hub_bp.route('/settings/interval', methods=['POST'])
@login_required
@roles_required('admin')
def update_interval():
    raw_val = (request.form.get('uptime_interval_seconds') or request.form.get('interval') or '').strip()
    try:
        val = int(raw_val)
        if val < 60 or val > 3600:
            raise ValueError()
    except (ValueError, TypeError):
        flash("Interval pemantauan harus berupa bilangan bulat antara 60 dan 3600 detik.", "danger")
        return redirect(url_for('settings_hub.hub'))

    set_hub_setting('uptime_interval_seconds', str(val), is_secret=False)
    flash("Interval pemantauan berhasil disimpan.", "success")
    return redirect(url_for('settings_hub.hub'))


@settings_hub_bp.route('/settings/api-key', methods=['POST'])
@login_required
@roles_required('admin')
def update_api_key():
    api_key = request.form.get('api_key', '').strip()
    if not api_key:
        if delete_hub_setting('api_key'):
            flash("API key di database dihapus, kembali ke environment variable.", "success")
        else:
            flash("Gagal menghapus API key dari database.", "danger")
        return redirect(url_for('settings_hub.hub'))

    try:
        set_hub_setting('api_key', api_key, is_secret=True)
    except ValueError:
        flash("Kunci enkripsi SETTINGS_ENCRYPTION_KEY belum dikonfigurasi.", "danger")
        return redirect(url_for('settings_hub.hub'))

    flash("API key berhasil disimpan.", "success")
    return redirect(url_for('settings_hub.hub'))
