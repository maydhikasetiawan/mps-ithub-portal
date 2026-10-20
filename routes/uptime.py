import os
import socket
import time
import urllib.request
import logging
import threading
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from routes.auth import login_required, roles_required
from database.db import get_db_connection, get_branding

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

    for m in monitors_list:
        cur.execute("""
            SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE status = 'UP') AS up
            FROM uptime_checks
            WHERE monitor_id = %s AND checked_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours';
        """, (m['id'],))
        row = cur.fetchone()
        tot = row['total'] or 0
        up = row['up'] or 0
        m['uptime_pct'] = round(up / tot * 100, 1) if tot > 0 else None

        cur.execute("""
            SELECT status, latency FROM uptime_checks
            WHERE monitor_id = %s ORDER BY checked_at DESC LIMIT 24;
        """, (m['id'],))
        checks = cur.fetchall()
        checks.reverse()
        up_lats = [c['latency'] for c in checks if c['status'] == 'UP' and c['latency'] is not None]
        max_lat = max(up_lats) if up_lats else 0
        spark = []
        for c in checks:
            if c['status'] == 'DOWN':
                spark.append({'h': 15, 'down': True})
            else:
                lat = c['latency'] or 0
                h = max(15, round(lat / max_lat * 100)) if max_lat > 0 else 15
                spark.append({'h': h, 'down': False})
        m['spark'] = spark

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
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            RETURNING id;
        """, (name, target, type_check, port, status, latency))
        new_row = cur.fetchone()
        monitor_id = new_row['id']
        cur.execute("""
            INSERT INTO uptime_checks (monitor_id, status, latency)
            VALUES (%s, %s, %s);
        """, (monitor_id, status, latency))
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
        cur.execute("""
            INSERT INTO uptime_checks (monitor_id, status, latency)
            VALUES (%s, %s, %s);
        """, (monitor_id, status, latency))
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
    cur.execute("DELETE FROM uptime_checks WHERE monitor_id = %s;", (monitor_id,))
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
            cur.execute("""
                INSERT INTO uptime_checks (monitor_id, status, latency)
                VALUES (%s, %s, %s);
            """, (monitor_id, status, latency))
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
        old_failures = m['consecutive_failures'] or 0
        old_alerted = m['is_alerted'] or False
        status, latency = check_target_health(m['target'], m['type'], m['port'])
        failures = old_failures + 1 if status == 'DOWN' else 0

        alert_type = None
        new_alerted = old_alerted
        if status == 'DOWN' and failures == 2 and not old_alerted:
            alert_type = 'DOWN'
            new_alerted = True
        elif status == 'UP' and old_alerted:
            alert_type = 'RECOVERED'
            new_alerted = False

        cur.execute("""
            UPDATE monitors
            SET status = %s, latency = %s, last_check = CURRENT_TIMESTAMP,
                consecutive_failures = %s, is_alerted = %s
            WHERE id = %s;
        """, (status, latency, failures, new_alerted, m['id']))
        cur.execute("""
            INSERT INTO uptime_checks (monitor_id, status, latency)
            VALUES (%s, %s, %s);
        """, (m['id'], status, latency))

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

    cur.execute("""
        DELETE FROM uptime_checks
        WHERE checked_at < CURRENT_TIMESTAMP - INTERVAL '30 days';
    """)

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
        token, chat_id, f"🔔 Tes koneksi Telegram {get_branding()['app_name']} — koneksi aktif."
    )
    if ok:
        flash("Koneksi Telegram aktif — pesan tes terkirim.", "success")
    else:
        flash(f"Koneksi Telegram GAGAL: {error}", "danger")
    return redirect(url_for('uptime.telegram_settings'))


def build_latency_svg(points, range_param):
    """Build a server-rendered SVG latency chart. Returns '' when there
    are no points. UP checks = polyline; DOWN checks (raw mode) = red
    dots at the baseline; hourly buckets with down_count > 0 get a red
    dot at the baseline too. Y-scale = max latency in the data (min 1)."""
    if not points:
        return ''

    if range_param == '24h':
        up_lats = [p['latency'] for p in points if p.get('status') == 'UP']
    else:
        up_lats = [p['avg_lat'] for p in points if p.get('avg_lat') is not None]

    raw_max = max(up_lats) if up_lats else 1.0
    max_lat = max(float(raw_max), 1.0)

    n = len(points)
    segments = []
    current_segment = []
    down_dots = []

    for i, p in enumerate(points):
        x = 20.0 if n == 1 else (20.0 + (680.0 * i / (n - 1)))
        if range_param == '24h':
            is_up = (p.get('status') == 'UP')
            lat = p.get('latency', 0)
            is_down = (p.get('status') == 'DOWN')
        else:
            is_up = (p.get('avg_lat') is not None)
            lat = p.get('avg_lat', 0) or 0
            is_down = (p.get('down_count', 0) > 0)

        if is_up:
            y = round(240.0 - (lat / max_lat) * 220.0, 1)
            current_segment.append(f"{round(x, 1)},{y}")
        else:
            if current_segment:
                segments.append(current_segment)
                current_segment = []

        if is_down:
            down_dots.append(f'<circle cx="{round(x, 1)}" cy="240" r="4" fill="#ef4444" />')

    if current_segment:
        segments.append(current_segment)

    polylines = []
    for seg in segments:
        if len(seg) == 1:
            pts_str = f"{seg[0]} {seg[0]}"
        else:
            pts_str = " ".join(seg)
        polylines.append(f'<polyline points="{pts_str}" fill="none" style="stroke: var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />')

    first_t = points[0]['t'].strftime('%d %b %H:%M') if hasattr(points[0]['t'], 'strftime') else str(points[0]['t'])
    last_t = points[-1]['t'].strftime('%d %b %H:%M') if hasattr(points[-1]['t'], 'strftime') else str(points[-1]['t'])

    half_max = int(round(max_lat / 2))
    full_max = int(round(max_lat))

    svg_parts = [
        '<svg viewBox="0 0 720 260" width="100%" style="height:auto; display:block;" xmlns="http://www.w3.org/2000/svg">',
        '<!-- Gridlines -->',
        '<line x1="20" y1="20" x2="700" y2="20" style="stroke: var(--line)" stroke-opacity="0.6" stroke-width="1" />',
        '<line x1="20" y1="75" x2="700" y2="75" style="stroke: var(--line)" stroke-opacity="0.6" stroke-width="1" />',
        '<line x1="20" y1="130" x2="700" y2="130" style="stroke: var(--line)" stroke-opacity="0.6" stroke-width="1" />',
        '<line x1="20" y1="185" x2="700" y2="185" style="stroke: var(--line)" stroke-opacity="0.6" stroke-width="1" />',
        '<line x1="20" y1="240" x2="700" y2="240" style="stroke: var(--line)" stroke-width="1" />',
        '<!-- Y Labels -->',
        f'<text x="25" y="25" style="fill: var(--faint)" font-size="10" font-family="Public Sans, sans-serif">{full_max} ms</text>',
        f'<text x="25" y="125" style="fill: var(--faint)" font-size="10" font-family="Public Sans, sans-serif">{half_max} ms</text>',
        '<text x="25" y="235" style="fill: var(--faint)" font-size="10" font-family="Public Sans, sans-serif">0 ms</text>',
        '<!-- Data -->',
        "".join(polylines),
        "".join(down_dots),
        '<!-- X Labels -->',
        f'<text x="20" y="255" style="fill: var(--muted)" font-size="11" font-family="Public Sans, sans-serif" text-anchor="start">{first_t}</text>',
        f'<text x="700" y="255" style="fill: var(--muted)" font-size="11" font-family="Public Sans, sans-serif" text-anchor="end">{last_t}</text>',
        '</svg>'
    ]

    return "".join(svg_parts)


# --- RIWAYAT DAN GRAFIK MONITOR ---
@uptime_bp.route('/<int:monitor_id>/history')
@login_required
@roles_required('admin', 'it', 'guest')
def history(monitor_id):
    range_param = request.args.get('range', '24h')
    if range_param not in ('24h', '7d', '30d'):
        range_param = '24h'

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM monitors WHERE id = %s;", (monitor_id,))
    monitor = cur.fetchone()
    if not monitor:
        cur.close()
        conn.close()
        flash("Monitor tidak ditemukan.", "danger")
        return redirect(url_for('uptime.index'))

    if range_param == '24h':
        cur.execute("""
            SELECT checked_at, status, latency FROM uptime_checks
            WHERE monitor_id = %s
              AND checked_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            ORDER BY checked_at ASC;
        """, (monitor_id,))
        rows = cur.fetchall()
        points = [
            {'t': r['checked_at'], 'status': r['status'], 'latency': r['latency']}
            for r in rows
        ]
        total = len(rows)
        up_count = sum(1 for r in rows if r['status'] == 'UP')
        down_count = total - up_count
        up_lat = [r['latency'] for r in rows if r['status'] == 'UP']
    else:
        days = '7 days' if range_param == '7d' else '30 days'
        cur.execute("""
            SELECT date_trunc('hour', checked_at) AS bucket,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'UP') AS up_count,
                   COUNT(*) FILTER (WHERE status = 'DOWN') AS down_count,
                   AVG(latency) FILTER (WHERE status = 'UP') AS avg_lat,
                   MIN(latency) FILTER (WHERE status = 'UP') AS min_lat,
                   MAX(latency) FILTER (WHERE status = 'UP') AS max_lat,
                   SUM(latency) FILTER (WHERE status = 'UP') AS sum_lat
            FROM uptime_checks
            WHERE monitor_id = %s
              AND checked_at >= CURRENT_TIMESTAMP - INTERVAL '""" + days + """'
            GROUP BY bucket
            ORDER BY bucket ASC;
        """, (monitor_id,))
        buckets = cur.fetchall()
        points = [
            {'t': b['bucket'], 'avg_lat': round(float(b['avg_lat']), 1) if b['avg_lat'] is not None else None,
             'down_count': b['down_count']}
            for b in buckets
        ]
        total = sum(b['total'] for b in buckets)
        up_count = sum(b['up_count'] for b in buckets)
        down_count = total - up_count
        bucket_mins = [float(b['min_lat']) for b in buckets if b['min_lat'] is not None]
        bucket_maxs = [float(b['max_lat']) for b in buckets if b['max_lat'] is not None]
        bucket_sum = sum(float(b['sum_lat']) for b in buckets if b['sum_lat'] is not None)

    cur.close()
    conn.close()

    uptime_pct = round(up_count / total * 100, 1) if total else 0.0
    if range_param == '24h':
        avg_lat = round(sum(up_lat) / len(up_lat), 1) if up_lat else None
        min_lat = round(min(up_lat), 1) if up_lat else None
        max_lat = round(max(up_lat), 1) if up_lat else None
    else:
        avg_lat = round(bucket_sum / up_count, 1) if up_count else None
        min_lat = round(min(bucket_mins), 1) if bucket_mins else None
        max_lat = round(max(bucket_maxs), 1) if bucket_maxs else None
    chart_svg = build_latency_svg(points, range_param)

    return render_template(
        'uptime/history.html',
        monitor=monitor, range_param=range_param, points=points,
        total=total, up_count=up_count, down_count=down_count,
        uptime_pct=uptime_pct, avg_lat=avg_lat, min_lat=min_lat,
        max_lat=max_lat, chart_svg=chart_svg, active_page='uptime',
    )


CHECK_INTERVAL_SECONDS = int(os.environ.get('UPTIME_CHECK_INTERVAL', 300))


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
