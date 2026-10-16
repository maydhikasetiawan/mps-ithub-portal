import csv
import io
from collections import Counter
from flask import Blueprint, render_template, request, Response, session, flash, redirect, url_for
from routes.auth import login_required
from database.db import get_db_connection
from datetime import datetime
from routes.tickets import compute_sla, format_duration

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

@reports_bp.route('/')
@login_required
def index():
    conn = get_db_connection()
    cur = conn.cursor()

    # Ambil kategori tiket untuk dropdown filter
    cur.execute("SELECT * FROM ticket_categories ORDER BY name ASC;")
    ticket_categories = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('reports/index.html', ticket_categories=ticket_categories, active_page='reports')

# --- EXPORT LAPORAN ASSETS (IPAM) ---
@reports_bp.route('/export/assets')
@login_required
def export_assets():
    category = request.args.get('category', '')
    status = request.args.get('status', '')
    include_deleted = request.args.get('include_deleted', 'false')

    conn = get_db_connection()
    cur = conn.cursor()

    query = "SELECT * FROM assets WHERE 1=1"
    params = []

    if include_deleted != 'true':
        query += " AND is_deleted = FALSE"

    if category:
        query += " AND category = %s"
        params.append(category)

    if status:
        query += " AND status = %s"
        params.append(status)

    query += " ORDER BY id DESC;"
    cur.execute(query, tuple(params))
    assets = cur.fetchall()
    cur.close()
    conn.close()

    # Generator File CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header block
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    username = session.get('username', '')
    filter_str = f"Kategori: {category or 'Semua'}; Status: {status or 'Semua'}; Termasuk Terhapus: {'Ya' if include_deleted == 'true' else 'Tidak'}"

    writer.writerow(['Laporan Aset IT'])
    writer.writerow(['Tanggal Dibuat Laporan', now_str])
    writer.writerow(['Dibuat Oleh', username])
    writer.writerow(['Filter', filter_str])
    writer.writerow([])

    # Summary block
    writer.writerow(['Ringkasan'])
    writer.writerow(['Total Aset', len(assets)])

    writer.writerow(['Berdasarkan Status'])
    status_counts = Counter(a['status'] for a in assets if a.get('status'))
    known_statuses = ['Procurement', 'Active', 'Under Repair', 'Retired']
    ordered_statuses = [st for st in known_statuses if status_counts.get(st, 0) > 0]
    other_statuses = sorted([st for st in status_counts if st not in known_statuses and status_counts[st] > 0])
    for st in ordered_statuses + other_statuses:
        writer.writerow([f"  - {st}", status_counts[st]])

    writer.writerow(['Berdasarkan Kategori'])
    category_counts = Counter(a['category'] for a in assets if a.get('category'))
    sorted_cats = sorted(category_counts.keys(), key=lambda c: (-category_counts[c], c))
    for cat in sorted_cats:
        writer.writerow([f"  - {cat}", category_counts[cat]])
    writer.writerow([])

    # Header Kolom Excel
    writer.writerow([
        'ID', 'Asset Tag', 'Nama Perangkat', 'Kategori', 'IP Address',
        'MAC Address', 'Serial Number', 'Status', 'Assigned To', 'Lokasi', 'Catatan',
        'Purchase Date', 'Warranty Expiry', 'Tanggal Terdaftar',
        'Terakhir Diperbarui', 'Diperbarui Oleh', 'Status Penghapusan', 'Alasan Penghapusan'
    ])

    for a in assets:
        created_str = a['created_at'].strftime('%Y-%m-%d %H:%M:%S') if a['created_at'] else ''
        updated_str = a['updated_at'].strftime('%Y-%m-%d %H:%M:%S') if a['updated_at'] else ''
        deleted_status = 'Terhapus/Archived' if a['is_deleted'] else 'Aktif'

        writer.writerow([
            a['id'],
            a['asset_tag'],
            a['name'],
            a['category'],
            a['ip_address'] or '',
            a['mac_address'] or '',
            a['serial_number'] or '',
            a['status'],
            a['assigned_to'] or '',
            a['location'] or '',
            a['notes'] or '',
            a['purchase_date'].strftime('%Y-%m-%d') if a['purchase_date'] else '',
            a['warranty_expiry'].strftime('%Y-%m-%d') if a['warranty_expiry'] else '',
            created_str,
            updated_str,
            a['updated_by'] or '',
            deleted_status,
            a['delete_reason'] or ''
        ])

    writer.writerow([])
    writer.writerow([f"Total Baris Data: {len(assets)}"])

    filename = f"Laporan_Aset_IT_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

    # Encoded UTF-8-SIG agar Microsoft Excel membuka titik koma/koma dengan rapi
    csv_data = '\ufeff' + output.getvalue()

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )

# --- EXPORT LAPORAN SERVICE DESK (TICKETS) ---
@reports_bp.route('/export/tickets')
@login_required
def export_tickets():
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    category = request.args.get('category', '')
    status = request.args.get('status', '')

    conn = get_db_connection()
    cur = conn.cursor()

    query = "SELECT * FROM tickets WHERE is_deleted = FALSE"
    params = []

    if start_date:
        query += " AND created_at >= %s"
        params.append(f"{start_date} 00:00:00")

    if end_date:
        query += " AND created_at <= %s"
        params.append(f"{end_date} 23:59:59")

    if category:
        query += " AND category = %s"
        params.append(category)

    if status:
        query += " AND status = %s"
        params.append(status)

    query += " ORDER BY id DESC;"
    cur.execute(query, tuple(params))
    tickets = cur.fetchall()

    activities_map = {}
    ratings_map = {}

    if tickets:
        ticket_ids = [t['id'] for t in tickets]

        # 2a. Activities aggregate: last activity and qualifying response
        cur.execute("""
            SELECT 
                ta.ticket_id,
                MAX(ta.created_at) AS last_activity,
                BOOL_OR(
                    ta.type IN ('comment', 'status', 'assignment') AND u.role IN ('admin', 'it')
                ) AS has_response
            FROM ticket_activities ta
            LEFT JOIN users u ON ta.actor = u.username
            WHERE ta.ticket_id = ANY(%s)
            GROUP BY ta.ticket_id;
        """, (ticket_ids,))
        activities_map = {row['ticket_id']: row for row in cur.fetchall()}

        # 2b. Ratings per ticket
        cur.execute("""
            SELECT ticket_id, rating
            FROM ticket_ratings
            WHERE ticket_id = ANY(%s);
        """, (ticket_ids,))
        ratings_map = {row['ticket_id']: row['rating'] for row in cur.fetchall()}

    cur.close()
    conn.close()

    now = datetime.now()
    ticket_slas = {}
    for t in tickets:
        act_info = activities_map.get(t['id'], {})
        has_resp = bool(act_info.get('has_response'))
        ticket_slas[t['id']] = compute_sla(t, has_response=has_resp, now=now)

    output = io.StringIO()
    writer = csv.writer(output)

    # 4. Header block
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    username = session.get('username', '')
    if not start_date and not end_date:
        period_str = 'Semua Periode'
    else:
        s_part = start_date if start_date else '-'
        e_part = end_date if end_date else '-'
        period_str = f"{s_part} s/d {e_part}"

    filter_str = f"Kategori: {category or 'Semua'}; Status: {status or 'Semua'}"

    writer.writerow(['Laporan IT Service Desk & Helpdesk'])
    writer.writerow(['Tanggal Dibuat Laporan', now_str])
    writer.writerow(['Dibuat Oleh', username])
    writer.writerow(['Periode', period_str])
    writer.writerow(['Filter', filter_str])
    writer.writerow([])

    # 5. Summary block
    writer.writerow(['Ringkasan'])
    writer.writerow(['Total Tiket', len(tickets)])

    writer.writerow(['Berdasarkan Status'])
    status_counts = Counter(t['status'] for t in tickets if t.get('status'))
    known_statuses = ['Open', 'In Progress', 'Resolved', 'Closed']
    ordered_statuses = [st for st in known_statuses if status_counts.get(st, 0) > 0]
    other_statuses = sorted([st for st in status_counts if st not in known_statuses and status_counts[st] > 0])
    for st in ordered_statuses + other_statuses:
        writer.writerow([f"  - {st}", status_counts[st]])

    writer.writerow(['Berdasarkan Kategori'])
    category_counts = Counter(t['category'] for t in tickets if t.get('category'))
    sorted_cats = sorted(category_counts.keys(), key=lambda c: (-category_counts[c], c))
    for cat in sorted_cats:
        writer.writerow([f"  - {cat}", category_counts[cat]])

    writer.writerow(['Berdasarkan Prioritas'])
    priority_counts = Counter(t['priority'] for t in tickets if t.get('priority'))
    known_priorities = ['Critical', 'High', 'Medium', 'Low']
    for p in known_priorities:
        if priority_counts.get(p, 0) > 0:
            writer.writerow([f"  - {p}", priority_counts[p]])
    other_priorities = sorted([p for p in priority_counts if p not in known_priorities and priority_counts[p] > 0])
    for p in other_priorities:
        writer.writerow([f"  - {p}", priority_counts[p]])

    durations = [
        (t['resolved_at'] - t['created_at']).total_seconds()
        for t in tickets
        if t.get('resolved_at') and t.get('created_at')
    ]
    if durations:
        avg_duration_sec = sum(durations) / len(durations)
        avg_duration_str = format_duration(avg_duration_sec)
    else:
        avg_duration_str = '-'
    writer.writerow(['Rata-rata Durasi Penyelesaian', avg_duration_str])

    total_tickets = len(tickets)
    if total_tickets > 0:
        compliant_count = sum(
            1 for t in tickets
            if ticket_slas.get(t['id']) and ticket_slas[t['id']].get('state') in ('met', 'ok')
        )
        sla_percent_str = f"{round(100 * compliant_count / total_tickets, 1)}%"
    else:
        sla_percent_str = '-'
    writer.writerow(['% SLA Terpenuhi', sla_percent_str])

    rated_values = [
        ratings_map[t['id']]
        for t in tickets
        if t['id'] in ratings_map and ratings_map[t['id']] is not None
    ]
    if rated_values:
        avg_csat = round(sum(rated_values) / len(rated_values), 1)
        csat_str = f"{avg_csat} / 5"
    else:
        csat_str = '-'
    writer.writerow(['Rata-rata CSAT', csat_str])
    writer.writerow([])

    # 6. Column header row + data rows, then footer
    writer.writerow([
        'ID', 'Kode Tiket', 'Judul Masalah', 'Kategori', 'Prioritas',
        'Status', 'Deskripsi Masalah', 'Pelapor', 'Tanggal Laporan',
        'Catatan Solusi / Resolution Note', 'Diselesaikan Oleh', 'Tanggal Selesai',
        'Assignee', 'SLA', 'Durasi Penyelesaian', 'CSAT', 'Terakhir Diperbarui'
    ])

    for t in tickets:
        created_str = t['created_at'].strftime('%Y-%m-%d %H:%M:%S') if t['created_at'] else ''
        resolved_str = t['resolved_at'].strftime('%Y-%m-%d %H:%M:%S') if t['resolved_at'] else ''
        assignee_str = t['assigned_to'] or ''
        sla = ticket_slas.get(t['id'])
        sla_str = sla['badge_text'] if sla and sla.get('badge_text') else '-'
        duration_str = format_duration((t['resolved_at'] - t['created_at']).total_seconds()) if t.get('resolved_at') and t.get('created_at') else '-'
        csat_val = ratings_map.get(t['id'], '')
        last_activity = activities_map.get(t['id'], {}).get('last_activity') or t['created_at']
        last_updated_str = last_activity.strftime('%Y-%m-%d %H:%M:%S') if last_activity else ''

        writer.writerow([
            t['id'],
            t['ticket_code'],
            t['title'],
            t['category'],
            t['priority'],
            t['status'],
            t['description'],
            t['created_by'],
            created_str,
            t['resolution_note'] or '',
            t['resolved_by'] or '',
            resolved_str,
            assignee_str,
            sla_str,
            duration_str,
            csat_val,
            last_updated_str
        ])

    writer.writerow([])
    writer.writerow([f"Total Baris Data: {len(tickets)}"])

    filename = f"Laporan_Service_Desk_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    csv_data = '\ufeff' + output.getvalue()

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )
