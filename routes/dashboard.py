from flask import Blueprint, render_template, session
from routes.auth import login_required
from database.db import get_db_connection
from datetime import date, timedelta

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@dashboard_bp.route('/dashboard')
@login_required
def index():
    conn = get_db_connection()
    cur = conn.cursor()

    # Total Aset Aktif
    cur.execute("SELECT COUNT(*) as count FROM assets WHERE is_deleted = FALSE;")
    total_assets = cur.fetchone()['count']

    # Tiket Open / In Progress
    cur.execute("SELECT COUNT(*) as count FROM tickets WHERE status IN ('Open', 'In Progress') AND is_deleted = FALSE;")
    open_tickets = cur.fetchone()['count']

    # Hitung Persentase Services Online dari Uptime Monitor
    cur.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status = 'UP' THEN 1 ELSE 0 END) as up_count FROM monitors;")
    monitor_stats = cur.fetchone()

    total_monitors = monitor_stats['total'] or 0
    up_monitors = monitor_stats['up_count'] or 0

    if total_monitors > 0:
        uptime_percentage = round((up_monitors / total_monitors) * 100, 1)
    else:
        uptime_percentage = 100.0  # Default 100% jika belum ada monitor

    # Pengingat Garansi Habis (aktif, warranty_expiry <= today + 30 days)
    today = date.today()
    threshold = today + timedelta(days=30)
    cur.execute("""
        SELECT id, asset_tag, name, warranty_expiry
        FROM assets
        WHERE is_deleted = FALSE
          AND (no_warranty IS NULL OR no_warranty = FALSE)
          AND warranty_expiry IS NOT NULL
          AND warranty_expiry <= %s
        ORDER BY warranty_expiry ASC;
    """, (threshold,))
    warranty_rows = cur.fetchall()

    expiring_warranties = []
    for row in warranty_rows:
        diff = (row['warranty_expiry'] - today).days
        if diff > 0:
            status_text = f"Aktif — habis dalam {diff} hari"
        elif diff == 0:
            status_text = "Habis hari ini"
        else:
            status_text = f"Sudah habis — {abs(diff)} hari lalu"
        expiring_warranties.append({
            'id': row['id'],
            'asset_tag': row['asset_tag'],
            'name': row['name'],
            'warranty_expiry': row['warranty_expiry'].strftime('%Y-%m-%d'),
            'status_text': status_text,
            'days_remaining': diff
        })

    cur.close()
    conn.close()

    return render_template('dashboard.html',
                           total_assets=total_assets,
                           open_tickets=open_tickets,
                           uptime_percentage=uptime_percentage,
                           expiring_warranties=expiring_warranties,
                           active_page='dashboard')
