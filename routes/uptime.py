import socket
import time
import urllib.request
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
    up_count = sum(1 for m in monitors_list if m['status'] == 'UP')
    down_count = sum(1 for m in monitors_list if m['status'] == 'DOWN')

    return render_template('uptime/index.html', monitors=monitors_list, total=total, up_count=up_count, down_count=down_count, active_page='uptime')

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

# --- TRIGGER CHECK SEMUA SERVICE SEKALIGUS ---
@uptime_bp.route('/check-all')
@login_required
@roles_required('admin', 'it', 'guest')
def check_all():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM monitors;")
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

    flash("Seluruh target service berhasil dipindai ulang!", "success")
    return redirect(url_for('uptime.index'))
