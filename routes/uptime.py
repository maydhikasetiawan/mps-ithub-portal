import socket
import time
import urllib.request
import logging
import threading
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from routes.auth import login_required, roles_required
from database.db import get_db_connection

uptime_bp = Blueprint('uptime', __name__, url_prefix='/uptime')

# Fungsi Pembantu untuk Health Check
def check_target_health(target, monitor_type='PING', port=None):
    start_time = time.time()
    try:
        if monitor_type == 'HTTP':
            url = target if target.startswith(('http://', 'https://')) else f"http://{target}"
            req = urllib.request.Request(url, headers={'User-Agent': 'MPS-ITHub Monitor'})
            with urllib.request.urlopen(req, timeout=3) as response:
                latency = int((time.time() - start_time) * 1000)
                if response.status in [200, 301, 302]:
                    return 'UP', latency
                return 'DOWN', latency
        else: # TCP / Port Check
            check_port = port if port else 80
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((target, int(check_port)))
            s.close()
            latency = int((time.time() - start_time) * 1000)
            return 'UP', latency
    except Exception:
        return 'DOWN', 0

def get_telegram_config():
    """Return (bot_token, chat_id) from the saved telegram_settings row.
    Returns ('', '') when not configured or on any read error."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT bot_token, chat_id FROM telegram_settings WHERE id = 1;")
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return row['bot_token'] or '', row['chat_id'] or ''
    except Exception:
        logging.exception("Failed to read Telegram settings")
    return '', ''


def send_telegram_message(token, chat_id, text):
    """Send one Telegram message. Returns (True, '') on success,
    (False, error) on failure. Never raises."""
    if not token or not chat_id:
        return False, "Telegram belum dikonfigurasi."
    try:
        payload = json.dumps({'chat_id': chat_id, 'text': text}).encode('utf-8')
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            response.read()
        return True, ''
    except Exception as exc:
        return False, str(exc)


def send_telegram_alert(text):
    """Best-effort alert sender for the scheduler: read saved config,
    send, log on failure. Never raises (must never break the loop)."""
    try:
        token, chat_id = get_telegram_config()
        ok, error = send_telegram_message(token, chat_id, text)
        if not ok:
            logging.warning("Telegram alert not sent: %s", error)
    except Exception:
        logging.exception("Failed to send Telegram alert")


# --- DASHBOARD UPTIME MONITOR ---
@uptime_bp.route('/')
@login_required
@roles_required('admin', 'it', 'guest')
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM monitors ORDER BY id DESC;")
    monitors_list = cur.fetchall()

    cur.execute("""
        SELECT a.*, mon.name AS monitor_name
        FROM uptime_alerts a
        JOIN monitors mon ON mon.id = a.monitor_id
        ORDER BY a.created_at DESC
        LIMIT 20;
    """)
    alerts = cur.fetchall()

    cur.close()
    conn.close()

    # Hitung Statistik Ringkasan
    total = len(monitors_list)
    up_count = sum(1 for m in monitors_list if m['enabled'] and m['status'] == 'UP')
    down_count = sum(1 for m in monitors_list if m['enabled'] and m['status'] == 'DOWN')
    paused_count = sum(1 for m in monitors_list if not m['enabled'])
    down_names = ", ".join(
        m['name'] for m in monitors_list if m['enabled'] and m['status'] == 'DOWN'
    )

    return render_template('uptime/index.html', monitors=monitors_list, total=total, up_count=up_count, down_count=down_count, paused_count=paused_count, alerts=alerts, down_names=down_names, active_page='uptime')

# --- TAMBAH TARGET MONITOR BARU ---
@uptime_bp.route('/add', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'it')
def add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        target = request.form.get('target', '').strip()
        type_check = request.form.get('type', 'TCP')
        port = request.form.get('port') or None

        status, latency = check_target_health(target, type_check, port)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO monitors (name, target, type, port, status, latency, last_check)
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP);
        """, (name, target, type_check, port, status, latency))
        conn.commit()
        cur.close()
        conn.close()

        flash(f"Target monitor '{name}' berhasil ditambahkan!", "success")
        return redirect(url_for('uptime.index'))

    return render_template('uptime/add.html', active_page='uptime')

# --- TRIGGER REFRESH / CHECK SEKARANG ---
@uptime_bp.route('/check/<int:monitor_id>')
@login_required
@roles_required('admin', 'it', 'guest')
def check_now(monitor_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM monitors WHERE id = %s;", (monitor_id,))
    monitor = cur.fetchone()

    if monitor:
        status, latency = check_target_health(monitor['target'], monitor['type'], monitor['port'])
        if status == 'UP':
            # UP resets the failure counter so the next down-episode
            # starts clean (otherwise a later DOWN would jump
            # failures 2 -> 3 and skip the == 2 alert condition).
            cur.execute("""
                UPDATE monitors
                SET status = %s, latency = %s, last_check = CURRENT_TIMESTAMP,
                    consecutive_failures = 0
                WHERE id = %s;
            """, (status, latency, monitor_id))
        else:
            cur.execute("""
                UPDATE monitors
                SET status = %s, latency = %s, last_check = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (status, latency, monitor_id))
        conn.commit()
        flash(f"Status '{monitor['name']}' berhasil diperbarui ({status} - {latency}ms).", "info")

    cur.close()
    conn.close()
    return redirect(url_for('uptime.index'))

# --- HAPUS TARGET MONITOR ---
@uptime_bp.route('/delete/<int:monitor_id>', methods=['POST'])
@login_required
@roles_required('admin', 'it')
def delete(monitor_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM uptime_alerts WHERE monitor_id = %s;", (monitor_id,))
    cur.execute("DELETE FROM monitors WHERE id = %s;", (monitor_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Target monitor berhasil dihapus.", "danger")
    return redirect(url_for('uptime.index'))

# --- TOGGLE MONITOR OTOMATIS (ON/OFF) ---
@uptime_bp.route('/toggle/<int:monitor_id>', methods=['POST'])
@login_required
@roles_required('admin', 'it')
def toggle(monitor_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM monitors WHERE id = %s;", (monitor_id,))
    monitor = cur.fetchone()

    if monitor:
        new_enabled = not monitor['enabled']
        # Toggling starts a fresh monitoring episode: reset the failure
        # counter so the next down-episode after re-enable alerts
        # correctly (otherwise a frozen failures = 2 would jump to 3
        # and skip the == 2 alert condition).
        cur.execute("UPDATE monitors SET enabled = %s, consecutive_failures = 0 WHERE id = %s;",
                    (new_enabled, monitor_id))
        conn.commit()
        state = "diaktifkan" if new_enabled else "dinonaktifkan"
        flash(f"Monitoring otomatis '{monitor['name']}' {state}.", "info")

    cur.close()
    conn.close()
    return redirect(url_for('uptime.index'))

# --- EDIT TARGET MONITOR ---
@uptime_bp.route('/edit/<int:monitor_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'it')
def edit(monitor_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM monitors WHERE id = %s;", (monitor_id,))
    monitor = cur.fetchone()

    if not monitor:
        cur.close()
        conn.close()
        return redirect(url_for('uptime.index'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        target = request.form.get('target', '').strip()
        type_check = request.form.get('type', 'TCP')
        port = request.form.get('port') or None
        enabled = 'enabled' in request.form

        if enabled:
            status, latency = check_target_health(target, type_check, port)
            if status == 'UP':
                # UP resets the failure counter (same reason as check_now).
                cur.execute("""
                    UPDATE monitors
                    SET name = %s, target = %s, type = %s, port = %s,
                        enabled = %s, status = %s, latency = %s,
                        last_check = CURRENT_TIMESTAMP,
                        consecutive_failures = 0
                    WHERE id = %s;
                """, (name, target, type_check, port, enabled, status, latency, monitor_id))
            else:
                cur.execute("""
                    UPDATE monitors
                    SET name = %s, target = %s, type = %s, port = %s,
                        enabled = %s, status = %s, latency = %s,
                        last_check = CURRENT_TIMESTAMP
                    WHERE id = %s;
                """, (name, target, type_check, port, enabled, status, latency, monitor_id))
        else:
            cur.execute("""
                UPDATE monitors
                SET name = %s, target = %s, type = %s, port = %s,
                    enabled = %s
                WHERE id = %s;
            """, (name, target, type_check, port, enabled, monitor_id))

        conn.commit()
        cur.close()
        conn.close()
        flash(f"Monitor '{name}' berhasil diperbarui.", "success")
        return redirect(url_for('uptime.index'))

    cur.close()
    conn.close()
    return render_template('uptime/edit.html', monitor=monitor, active_page='uptime')

def run_all_checks():
    """Re-check every enabled monitor and persist status/latency/last_check.
    Request-free: safe to call from a route OR from the scheduler thread.
    Opens and closes its OWN db connection (never share across threads).
    Fires DOWN / RECOVERED alerts on transitions (see design decisions)."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM monitors WHERE enabled = TRUE;")
    monitors_list = cur.fetchall()
    pending_telegrams = []

    for m in monitors_list:
        old_status = m['status']
        old_failures = m['consecutive_failures'] or 0
        status, latency = check_target_health(m['target'], m['type'], m['port'])
        failures = old_failures + 1 if status == 'DOWN' else 0
        cur.execute("""
            UPDATE monitors
            SET status = %s, latency = %s, last_check = CURRENT_TIMESTAMP,
                consecutive_failures = %s
            WHERE id = %s;
        """, (status, latency, failures, m['id']))

        alert_type = None
        if status == 'DOWN' and failures == 2:
            alert_type = 'DOWN'
        elif status == 'UP' and old_status == 'DOWN' and old_failures >= 2:
            alert_type = 'RECOVERED'

        if alert_type:
            if alert_type == 'DOWN':
                message = f"🔴 {m['name']} DOWN — tidak merespons ({m['target']})"
            else:
                message = f"🟢 {m['name']} pulih — kembali ONLINE ({m['target']})"
            cur.execute("""
                INSERT INTO uptime_alerts (monitor_id, alert_type, message)
                VALUES (%s, %s, %s);
            """, (m['id'], alert_type, message))
            pending_telegrams.append(message)

    conn.commit()
    cur.close()
    conn.close()

    # Telegram AFTER commit: alert rows are persisted even if Telegram fails.
    for text in pending_telegrams:
        send_telegram_alert(text)

# --- PENGATURAN TELEGRAM (ADMIN ONLY) ---
@uptime_bp.route('/telegram-settings', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def telegram_settings():
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        token = request.form.get('bot_token', '').strip()
        chat_id = request.form.get('chat_id', '').strip()
        # Empty token field = keep the saved token. To disable Telegram,
        # clear the Chat ID and Save.
        if token:
            cur.execute("""
                UPDATE telegram_settings
                SET bot_token = %s, chat_id = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1;
            """, (token, chat_id))
        else:
            cur.execute("""
                UPDATE telegram_settings
                SET chat_id = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1;
            """, (chat_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Pengaturan Telegram berhasil disimpan.", "success")
        return redirect(url_for('uptime.telegram_settings'))

    cur.execute("SELECT * FROM telegram_settings WHERE id = 1;")
    settings = cur.fetchone()
    cur.close()
    conn.close()
    return render_template(
        'uptime/telegram_settings.html', settings=settings, active_page='uptime'
    )


@uptime_bp.route('/telegram-test', methods=['POST'])
@login_required
@roles_required('admin')
def telegram_test():
    token, chat_id = get_telegram_config()
    ok, error = send_telegram_message(
        token, chat_id, "🔔 Tes koneksi Telegram MPS-ITHub — koneksi aktif."
    )
    if ok:
        flash("Koneksi Telegram aktif — pesan tes terkirim.", "success")
    else:
        flash(f"Koneksi Telegram GAGAL: {error}", "danger")
    return redirect(url_for('uptime.telegram_settings'))

CHECK_INTERVAL_SECONDS = 300  # 5 minutes


def _scheduler_loop():
    """Run checks immediately, then every CHECK_INTERVAL_SECONDS, forever.
    Any exception is logged and the loop CONTINUES — a failed run must
    never kill the scheduler."""
    while True:
        try:
            run_all_checks()
        except Exception:
            logging.exception("Uptime scheduler run failed")
        time.sleep(CHECK_INTERVAL_SECONDS)


def start_uptime_scheduler():
    # Assumes exactly 1 Gunicorn worker (current production). If workers
    # ever increase, this scheduler MUST be reworked (duplicate runs) —
    # e.g. a dedicated scheduler process or a DB advisory lock.
    thread = threading.Thread(
        target=_scheduler_loop, daemon=True, name="uptime-scheduler"
    )
    thread.start()
    logging.info(
        "Uptime scheduler started (interval %ss)", CHECK_INTERVAL_SECONDS
    )

# --- TRIGGER CHECK SEMUA SERVICE SEKALIGUS ---
@uptime_bp.route('/check-all')
@login_required
@roles_required('admin', 'it', 'guest')
def check_all():
    run_all_checks()
    flash("Seluruh target service berhasil dipindai ulang!", "success")
    return redirect(url_for('uptime.index'))
