import html
from flask import Blueprint, render_template, session
from routes.auth import login_required
from database.db import get_db_connection
from datetime import date, timedelta

dashboard_bp = Blueprint('dashboard', __name__)


def build_daily_vertical_svg(series):
    """Build server-rendered SVG vertical bar chart for 30-day ticket trend. Empty data returns ''."""
    if not series or all(p['count'] == 0 for p in series):
        return ''
    max_count = max(p['count'] for p in series)
    slot_w, bar_w = 680.0 / len(series), 14.0
    elements = [
        '<svg viewBox="0 0 720 220" width="100%" style="height:auto; display:block;" xmlns="http://www.w3.org/2000/svg">',
        '<line x1="20" y1="175" x2="700" y2="175" style="stroke: var(--line)" stroke-width="1" />',
        '<line x1="20" y1="40" x2="700" y2="40" style="stroke: var(--line)" stroke-opacity="0.6" stroke-width="1" stroke-dasharray="4" />',
    ]
    for i, p in enumerate(series):
        xc = round(20.0 + i * slot_w + (slot_w / 2.0), 1)
        bx = round(xc - (bar_w / 2.0), 1)
        val = p['count']
        bh = round((val / max_count) * 125.0, 1) if val > 0 else 0
        by = round(175.0 - bh, 1)
        if val > 0:
            elements.append(f'<rect x="{bx}" y="{by}" width="{bar_w}" height="{bh}" style="fill: var(--accent)" rx="2" />')
            elements.append(f'<text x="{xc}" y="{by - 4}" style="fill: var(--text)" font-size="9" font-family="Public Sans, sans-serif" font-weight="bold" text-anchor="middle">{val}</text>')
        else:
            elements.append(f'<text x="{xc}" y="169" style="fill: var(--faint)" font-size="8" font-family="Public Sans, sans-serif" text-anchor="middle">0</text>')
        lbl = html.escape(str(p['label']))
        elements.append(f'<text x="{xc}" y="188" style="fill: var(--muted)" font-size="8" font-family="Public Sans, sans-serif" text-anchor="end" transform="rotate(-45 {xc} 188)">{lbl}</text>')
    elements.append('</svg>')
    return ''.join(elements)


def build_horizontal_bar_svg(items):
    """Build server-rendered SVG horizontal bar chart. Empty data returns ''."""
    if not items or all(it['count'] == 0 for it in items):
        return ''
    max_count = max(it['count'] for it in items)
    row_h, pad = 36, 15
    h = pad * 2 + len(items) * row_h
    elements = [
        f'<svg viewBox="0 0 720 {h}" width="100%" style="height:auto; display:block;" xmlns="http://www.w3.org/2000/svg">',
        f'<line x1="180" y1="{pad}" x2="180" y2="{h - pad}" style="stroke: var(--line)" stroke-width="1" />',
    ]
    for i, it in enumerate(items):
        y = pad + i * row_h
        val = it['count']
        color = it.get('color', '#38bdf8')
        bw = round((val / max_count) * 450.0, 1) if val > 0 else 0
        ty = y + 23
        lbl = html.escape(str(it['label']))
        elements.append(f'<text x="170" y="{ty}" style="fill: var(--muted)" font-size="12" font-family="Public Sans, sans-serif" text-anchor="end">{lbl}</text>')
        if bw > 0:
            elements.append(f'<rect x="180" y="{y + 8}" width="{bw}" height="20" fill="{color}" rx="3" />')
        elements.append(f'<text x="{round(180 + bw + 10, 1)}" y="{ty}" style="fill: var(--text)" font-size="12" font-weight="bold" font-family="Public Sans, sans-serif" text-anchor="start">{val}</text>')
    elements.append('</svg>')
    return ''.join(elements)


def format_trend_delta(delta):
    return f"+{delta}" if delta > 0 else (f"{delta}" if delta < 0 else "0")


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

    # a. Tickets per category
    cur.execute("""
        SELECT category, COUNT(*) as count
        FROM tickets
        WHERE is_deleted = FALSE
        GROUP BY category
        ORDER BY count DESC;
    """)
    cat_rows = cur.fetchall()
    category_items = [{'label': r['category'] or 'Lainnya', 'count': r['count'], 'color': '#38bdf8'} for r in cat_rows]
    total_tickets_cat = sum(it['count'] for it in category_items)
    top_category = category_items[0]['label'] if category_items else '-'

    # b. Tickets created per day for the last 30 days (inclusive of today)
    cur.execute("""
        SELECT date_trunc('day', created_at)::date AS day, COUNT(*) as count
        FROM tickets
        WHERE is_deleted = FALSE
          AND created_at >= CURRENT_DATE - INTERVAL '29 days'
        GROUP BY date_trunc('day', created_at)
        ORDER BY day ASC;
    """)
    created_rows = cur.fetchall()
    created_by_day = {}
    for r in created_rows:
        raw_d = r['day']
        d = raw_d.date() if hasattr(raw_d, 'date') else (date.fromisoformat(raw_d[:10]) if isinstance(raw_d, str) else raw_d)
        created_by_day[d] = r['count']

    daily_series = [{'date': today - timedelta(days=i), 'label': (today - timedelta(days=i)).strftime('%d/%m'), 'count': created_by_day.get(today - timedelta(days=i), 0)} for i in range(29, -1, -1)]
    total_created_30d = sum(p['count'] for p in daily_series)
    avg_created_per_day = round(total_created_30d / 30.0, 1)

    # Created trend: days 0-6 vs days 7-13
    created_this_week = sum(p['count'] for p in daily_series[-7:])
    created_prev_week = sum(p['count'] for p in daily_series[-14:-7])
    created_delta = created_this_week - created_prev_week
    created_delta_str = format_trend_delta(created_delta)

    # c. Tickets per status
    cur.execute("SELECT status, COUNT(*) as count FROM tickets WHERE is_deleted = FALSE GROUP BY status;")
    t_status_map = {r['status']: r['count'] for r in cur.fetchall()}
    t_colors = {'Open': '#f97316', 'In Progress': '#facc15', 'Resolved': '#34d399', 'Closed': '#ef4444'}
    ticket_status_items = [{'label': s, 'count': t_status_map.pop(s, 0), 'color': t_colors.get(s, '#38bdf8')} for s in ['Open', 'In Progress', 'Resolved', 'Closed']]
    ticket_status_items += [{'label': s, 'count': c, 'color': t_colors.get(s, '#38bdf8')} for s, c in t_status_map.items()]

    # d. Assets per status
    cur.execute("SELECT status, COUNT(*) as count FROM assets WHERE is_deleted = FALSE GROUP BY status;")
    a_status_map = {r['status']: r['count'] for r in cur.fetchall()}
    a_colors = {'Procurement': '#facc15', 'Active': '#34d399', 'Under Repair': '#fbbf24', 'Retired': '#ef4444'}
    asset_status_items = [{'label': s, 'count': a_status_map.pop(s, 0), 'color': a_colors.get(s, '#38bdf8')} for s in ['Procurement', 'Active', 'Under Repair', 'Retired']]
    asset_status_items += [{'label': s, 'count': c, 'color': a_colors.get(s, '#38bdf8')} for s, c in a_status_map.items()]

    # e. Tickets resolved per week
    cur.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN resolved_at >= CURRENT_DATE - INTERVAL '7 days' THEN 1 ELSE 0 END), 0) AS resolved_this_week,
            COALESCE(SUM(CASE WHEN resolved_at >= CURRENT_DATE - INTERVAL '14 days' AND resolved_at < CURRENT_DATE - INTERVAL '7 days' THEN 1 ELSE 0 END), 0) AS resolved_prev_week
        FROM tickets
        WHERE is_deleted = FALSE
          AND resolved_at IS NOT NULL;
    """)
    res_row = cur.fetchone()
    resolved_this_week = int(res_row['resolved_this_week'] or 0)
    resolved_prev_week = int(res_row['resolved_prev_week'] or 0)
    resolved_delta = resolved_this_week - resolved_prev_week
    resolved_delta_str = format_trend_delta(resolved_delta)

    # SVG charts
    daily_chart_svg = build_daily_vertical_svg(daily_series)
    category_chart_svg = build_horizontal_bar_svg(category_items)
    ticket_status_chart_svg = build_horizontal_bar_svg(ticket_status_items)
    asset_status_chart_svg = build_horizontal_bar_svg(asset_status_items)

    # enabled-based monitor counts + down_names
    cur.execute("""
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN status = 'UP' THEN 1 ELSE 0 END), 0) AS up,
               COALESCE(SUM(CASE WHEN status = 'DOWN' THEN 1 ELSE 0 END), 0) AS down
        FROM monitors WHERE enabled = TRUE;
    """)
    m_enabled = cur.fetchone()
    active_monitors = int(m_enabled['total'] or 0)
    up_monitors_e = int(m_enabled['up'] or 0)

    cur.execute("SELECT name FROM monitors WHERE enabled = TRUE AND status = 'DOWN' ORDER BY name;")
    down_names = [r['name'] for r in cur.fetchall()]

    paused_monitors = total_monitors - active_monitors

    # high-priority open tickets
    cur.execute("""
        SELECT COUNT(*) AS count FROM tickets
        WHERE status IN ('Open', 'In Progress') AND priority IN ('High', 'Critical') AND is_deleted = FALSE;
    """)
    high_priority_open = int(cur.fetchone()['count'] or 0)

    # asset status split
    cur.execute("SELECT COUNT(*) AS count FROM assets WHERE status = 'Active' AND is_deleted = FALSE;")
    active_assets = int(cur.fetchone()['count'] or 0)
    cur.execute("SELECT COUNT(*) AS count FROM assets WHERE status = 'Under Repair' AND is_deleted = FALSE;")
    repair_assets = int(cur.fetchone()['count'] or 0)

    # users + departments
    cur.execute("SELECT COUNT(*) AS count FROM users WHERE is_deleted = FALSE;")
    total_users = int(cur.fetchone()['count'] or 0)
    cur.execute("SELECT COUNT(*) AS count FROM departments;")
    total_departments = int(cur.fetchone()['count'] or 0)

    # Activity feed (top 5, newest first)
    recent_activities = []
    try:
        cur.execute("""
            SELECT ta.created_at, ta.actor, ta.content, t.ticket_code
            FROM ticket_activities ta JOIN tickets t ON t.id = ta.ticket_id
            ORDER BY ta.created_at DESC LIMIT 8;
        """)
        t_acts = cur.fetchall()

        cur.execute("""
            SELECT aa.created_at, aa.actor, aa.action, aa.field_name, aa.old_value, aa.new_value, a.asset_tag, a.name
            FROM asset_activities aa JOIN assets a ON a.id = aa.asset_id
            ORDER BY aa.created_at DESC LIMIT 8;
        """)
        a_acts = cur.fetchall()

        raw_feed = []
        for r in t_acts:
            raw_feed.append({
                'created_at': r['created_at'],
                'source': 'ticket',
                'title': f"Tiket {r['ticket_code']}",
                'text': r['content'],
            })

        for r in a_acts:
            act = r['action']
            actor = r['actor'] or 'system'
            if act == 'created':
                txt = f"Aset dibuat oleh {actor}."
            elif act == 'soft-deleted':
                txt = "Aset dipindahkan ke Riwayat Terhapus."
            elif act == 'restored':
                txt = "Aset dikembalikan dari Riwayat Terhapus."
            elif act == 'updated':
                old_val = r['old_value'] or '-'
                new_val = r['new_value'] or '-'
                txt = f"{r['field_name']} diubah: {old_val} → {new_val}"
            else:
                txt = str(act)

            raw_feed.append({
                'created_at': r['created_at'],
                'source': 'asset',
                'title': r['asset_tag'] or r['name'] or 'Aset',
                'text': txt,
            })

        raw_feed.sort(key=lambda x: x['created_at'], reverse=True)
        for item in raw_feed[:5]:
            dt = item['created_at']
            time_str = dt.strftime('%d %b %Y, %H:%M') if hasattr(dt, 'strftime') else str(dt)
            recent_activities.append({
                'source': item['source'],
                'title': item['title'],
                'text': item['text'],
                'time': time_str,
            })
    except Exception:
        recent_activities = []

    cur.close()
    conn.close()

    return render_template(
        'dashboard.html',
        total_assets=total_assets,
        open_tickets=open_tickets,
        uptime_percentage=uptime_percentage,
        expiring_warranties=expiring_warranties,
        daily_chart_svg=daily_chart_svg,
        total_created_30d=total_created_30d,
        avg_created_per_day=avg_created_per_day,
        category_chart_svg=category_chart_svg,
        total_tickets_cat=total_tickets_cat,
        top_category=top_category,
        ticket_status_chart_svg=ticket_status_chart_svg,
        asset_status_chart_svg=asset_status_chart_svg,
        created_this_week=created_this_week,
        created_prev_week=created_prev_week,
        created_delta_str=created_delta_str,
        resolved_this_week=resolved_this_week,
        resolved_prev_week=resolved_prev_week,
        resolved_delta_str=resolved_delta_str,
        active_monitors=active_monitors,
        up_monitors_e=up_monitors_e,
        down_names=down_names,
        paused_monitors=paused_monitors,
        high_priority_open=high_priority_open,
        active_assets=active_assets,
        repair_assets=repair_assets,
        total_users=total_users,
        total_departments=total_departments,
        recent_activities=recent_activities,
        active_page='dashboard'
    )
