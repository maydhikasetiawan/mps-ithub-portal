import socket
import time
import urllib.request
import logging
import threading
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

# --- DASHBOARD UPTIME MONITOR ---
@uptime_bp.route('/')
@login_required
@roles_required('admin', 'it', 'guest')
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM monitors ORDER BY id DESC;")
    monitors_list = cur.fetchall()
    cur.close()
    conn.close()

    # Hitung Statistik Ringkasan
    total = len(monitors_list)
    up_count = sum(1 for m in monitors_list if m['enabled'] and m['status'] == 'UP')
    down_count = sum(1 for m in monitors_list if m['enabled'] and m['status'] == 'DOWN')
    paused_count = sum(1 for m in monitors_list if not m['enabled'])

    return render_template('uptime/index.html', monitors=monitors_list, total=total, up_count=up_count, down_count=down_count, paused_count=paused_count, active_page='uptime')

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
        cur.execute("UPDATE monitors SET enabled = %s WHERE id = %s;",
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
    """Re-check every monitor and persist status/latency/last_check.
    Request-free: safe to call from a route OR from the scheduler thread.
    Opens and closes its OWN db connection (never share across threads)."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM monitors WHERE enabled = TRUE;")
    monitors_list = cur.fetchall()

    for m in monitors_list:
        status, latency = check_target_health(m['target'], m['type'], m['port'])
        cur.execute("""
            UPDATE monitors
            SET status = %s, latency = %s, last_check = CURRENT_TIMESTAMP
            WHERE id = %s;
        """, (status, latency, m['id']))

    conn.commit()
    cur.close()
    conn.close()

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
