from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file, abort, jsonify
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from routes.auth import login_required, roles_required
from database.db import get_db_connection
from datetime import datetime, timezone
import os
import json
import urllib.request
import uuid
import mimetypes
import threading
import time
from psycopg2.extras import Json
from PIL import Image

tickets_bp = Blueprint('tickets', __name__, url_prefix='/tickets')

PER_PAGE = 20

# SLA Target Constants (calendar hours from created_at)
SLA_TARGETS = {
    'Critical': {'response': 1, 'resolution': 4},
    'High': {'response': 2, 'resolution': 8},
    'Medium': {'response': 4, 'resolution': 24},
    'Low': {'response': 8, 'resolution': 72},
}

def format_duration(seconds):
    if seconds is None:
        return "-"
    total_minutes = int(seconds // 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours > 0:
        return f"{hours} jam {minutes} menit"
    return f"{minutes} menit"

def compute_sla(ticket, activities=None, has_response=None, now=None):
    if not ticket or not ticket.get('created_at'):
        return None

    if now is None:
        now = datetime.now()

    priority = ticket.get('priority', 'Medium')
    targets = SLA_TARGETS.get(priority, SLA_TARGETS['Medium'])
    status = ticket.get('status', 'Open')
    created_at = ticket['created_at']
    resolved_at = ticket.get('resolved_at')

    # 1. Tiket Resolved/Closed: bandingkan (resolved_at - created_at) terhadap target resolusi
    if status in ['Resolved', 'Closed']:
        target_hours = targets['resolution']
        target_label = f"Target resolusi: {target_hours} jam"
        end_time = resolved_at if resolved_at else now
        elapsed = end_time - created_at
        elapsed_hours = max(0.0, elapsed.total_seconds() / 3600.0)

        if elapsed_hours <= target_hours:
            state = 'met'
            badge_text = 'SLA Terpenuhi'
        else:
            state = 'breached'
            badge_text = 'SLA Terlewati'

        return {
            'state': state,
            'badge_text': badge_text,
            'target_type': 'resolution',
            'target_hours': target_hours,
            'target_label': target_label,
            'elapsed_hours': elapsed_hours,
            'elapsed_text': format_duration(elapsed.total_seconds()),
            'elapsed_label': 'Waktu penyelesaian' if resolved_at else 'Waktu berjalan',
        }

    # 2. Tiket Open / In Progress
    if has_response is None:
        if activities is not None:
            has_response = any(
                act.get('type') in ['comment', 'status', 'assignment'] and act.get('actor_role') in ['admin', 'it']
                for act in activities
            )
        else:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT 1 FROM ticket_activities ta
                JOIN users u ON ta.actor = u.username
                WHERE ta.ticket_id = %s
                  AND ta.type IN ('comment', 'status', 'assignment')
                  AND u.role IN ('admin', 'it')
                LIMIT 1;
            """, (ticket['id'],))
            has_response = bool(cur.fetchone())
            cur.close()
            conn.close()

    elapsed = now - created_at
    elapsed_hours = max(0.0, elapsed.total_seconds() / 3600.0)

    # 3. Not yet responded vs Responded
    if not has_response:
        target_hours = targets['response']
        target_label = f"Target respon: {target_hours} jam"
        target_type = 'response'
        elapsed_label = 'Waktu respon berjalan'
    else:
        target_hours = targets['resolution']
        target_label = f"Target resolusi: {target_hours} jam"
        target_type = 'resolution'
        elapsed_label = 'Waktu resolusi berjalan'

    if elapsed_hours > target_hours:
        state = 'breached'
        badge_text = 'SLA Terlewati'
    elif elapsed_hours >= 0.8 * target_hours:
        state = 'approaching'
        badge_text = 'Mendekati SLA'
    else:
        state = 'ok'
        badge_text = None

    return {
        'state': state,
        'badge_text': badge_text,
        'target_type': target_type,
        'target_hours': target_hours,
        'target_label': target_label,
        'elapsed_hours': elapsed_hours,
        'elapsed_text': format_duration(elapsed.total_seconds()),
        'elapsed_label': elapsed_label,
    }

def enqueue_webhook(event, ticket, actor):
    """Queue a webhook delivery (async). Never raises: webhook failure must
    never break the ticket flow."""
    webhook_url = os.environ.get('WEBHOOK_URL', '').strip()
    if not webhook_url:
        return
    payload = {
        'event': event,
        'ticket_code': ticket.get('ticket_code'),
        'ticket_id': ticket.get('id'),
        'title': ticket.get('title'),
        'status': ticket.get('status'),
        'priority': ticket.get('priority'),
        'assigned_to': ticket.get('assigned_to') or None,
        'actor': actor,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'url': f"/tickets/{ticket.get('id')}",
    }
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO webhook_deliveries
               (event, ticket_id, ticket_code, payload, webhook_url)
               VALUES (%s, %s, %s, %s, %s) RETURNING id;""",
            (event, ticket.get('id'), ticket.get('ticket_code'),
             Json(payload), webhook_url)
        )
        delivery_id = cur.fetchone()['id']
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Webhook enqueue failed: {e}")
        return
    threading.Thread(target=_deliver_webhook, args=(delivery_id,), daemon=True).start()


def _deliver_webhook(delivery_id):
    """Delivery worker: up to 3 attempts with backoff (2s, 4s)."""
    try:
        for attempt in (1, 2, 3):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM webhook_deliveries WHERE id = %s;", (delivery_id,))
            row = cur.fetchone()
            if not row or row['status'] != 'pending':
                cur.close()
                conn.close()
                return
            payload = row['payload']
            webhook_url = row['webhook_url']
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                webhook_url, data=data,
                headers={'Content-Type': 'application/json'}, method='POST')
            error = None
            status_code = None
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    status_code = resp.status
                if 200 <= status_code < 300:
                    cur.execute(
                        """UPDATE webhook_deliveries
                           SET status='delivered', attempts=%s, response_status=%s,
                               last_error=NULL, delivered_at=CURRENT_TIMESTAMP
                           WHERE id=%s;""",
                        (attempt, status_code, delivery_id))
                    conn.commit()
                    cur.close()
                    conn.close()
                    return
                error = f"HTTP {status_code}"
            except Exception as e:
                error = str(e)[:500]
            cur.execute(
                """UPDATE webhook_deliveries
                   SET attempts=%s, response_status=%s, last_error=%s,
                       status=CASE WHEN %s >= 3 THEN 'failed' ELSE 'pending' END
                   WHERE id=%s;""",
                (attempt, status_code, error, attempt, delivery_id))
            conn.commit()
            cur.close()
            conn.close()
            if attempt < 3:
                time.sleep(2 ** attempt)
    except Exception as e:
        print(f"Webhook delivery failed: {e}")

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'txt', 'log', 'doc', 'docx', 'xls', 'xlsx', 'csv'}
MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_ATTACHMENTS_PER_TICKET = 2

def get_upload_folder():
    folder = os.environ.get('UPLOAD_FOLDER', 'uploads')
    if not os.path.isabs(folder):
        folder = os.path.abspath(folder)
    os.makedirs(folder, exist_ok=True)
    return folder

def format_file_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

def handle_ticket_attachments(ticket_id, files, uploader):
    valid_files = [f for f in files if f and f.filename and f.filename.strip()]
    if not valid_files:
        return True

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as count FROM ticket_attachments WHERE ticket_id = %s;", (ticket_id,))
    existing_count = cur.fetchone()['count']

    if existing_count + len(valid_files) > MAX_ATTACHMENTS_PER_TICKET:
        cur.close()
        conn.close()
        flash(f"Maksimal {MAX_ATTACHMENTS_PER_TICKET} lampiran per tiket. Unggahan dibatalkan.", "danger")
        return False

    for f in valid_files:
        filename = f.filename or ''
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        if ext not in ALLOWED_EXTENSIONS:
            cur.close()
            conn.close()
            flash(f"Ekstensi file '{filename}' tidak diizinkan.", "danger")
            return False

        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(0)
        if size > MAX_ATTACHMENT_SIZE:
            cur.close()
            conn.close()
            flash(f"File '{filename}' melebihi batas ukuran 5 MB.", "danger")
            return False
        if size == 0:
            cur.close()
            conn.close()
            flash(f"File '{filename}' kosong.", "danger")
            return False

    upload_folder = get_upload_folder()

    try:
        original_filenames = []
        for f in valid_files:
            filename = f.filename or ''
            ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
            orig_name = secure_filename(filename) or f"file.{ext}"
            original_filenames.append(orig_name)

            if ext in {'png', 'jpg', 'jpeg', 'webp'}:
                try:
                    img = Image.open(f)
                    if img.mode in ('RGBA', 'LA', 'P'):
                        img = img.convert('RGB')
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')

                    max_dim = 1920
                    width, height = img.size
                    if max(width, height) > max_dim:
                        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

                    stored_filename = f"{uuid.uuid4().hex}.jpg"
                    dest_path = os.path.join(upload_folder, stored_filename)
                    img.save(dest_path, format='JPEG', quality=70, optimize=True)
                    stored_size = os.path.getsize(dest_path)
                    mime_type = 'image/jpeg'
                except Exception:
                    cur.close()
                    conn.close()
                    flash(f"File gambar '{filename}' tidak dapat diproses atau rusak.", "danger")
                    return False
            elif ext == 'gif':
                stored_filename = f"{uuid.uuid4().hex}.gif"
                dest_path = os.path.join(upload_folder, stored_filename)
                f.save(dest_path)
                stored_size = os.path.getsize(dest_path)
                mime_type = 'image/gif'
            else:
                stored_filename = f"{uuid.uuid4().hex}.{ext}"
                dest_path = os.path.join(upload_folder, stored_filename)
                f.save(dest_path)
                stored_size = os.path.getsize(dest_path)
                mime_type = mimetypes.guess_type(orig_name)[0] or 'application/octet-stream'

            cur.execute("""
                INSERT INTO ticket_attachments (ticket_id, stored_filename, original_filename, size_bytes, mime_type, uploader)
                VALUES (%s, %s, %s, %s, %s, %s);
            """, (ticket_id, stored_filename, orig_name, stored_size, mime_type, uploader))

        cur.execute("""
            INSERT INTO ticket_activities (ticket_id, actor, type, content)
            VALUES (%s, %s, 'attachment', %s);
        """, (ticket_id, uploader, f"Attachment uploaded by {uploader}: {', '.join(original_filenames)}"))

        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        flash(f"Terjadi kesalahan saat menyimpan lampiran: {e}", "danger")
        return False

def generate_ticket_code():
    today_str = datetime.now().strftime('%Y%m%d')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as count FROM tickets WHERE ticket_code LIKE %s;", (f'TCK-{today_str}-%',))
    count = cur.fetchone()['count'] + 1
    cur.close()
    conn.close()
    return f"TCK-{today_str}-{count:03d}"

# --- DAFTAR TIKET ---
@tickets_bp.route('/')
@login_required
@roles_required('admin', 'it', 'user', 'guest')
def index():
    status_filter = request.args.get('status', '')
    assignee_filter = request.args.get('assignee', 'all').strip()
    search_query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int) or 1
    page = max(1, page)
    user_role = session.get('role', 'guest')
    username = session.get('username')

    conn = get_db_connection()
    cur = conn.cursor()

    where_clause = "WHERE is_deleted = FALSE"
    params = []

    # Regular User dan Guest hanya melihat tiket miliknya sendiri
    if user_role in ('user', 'guest'):
        where_clause += " AND created_by = %s"
        params.append(username)

    if status_filter:
        where_clause += " AND status = %s"
        params.append(status_filter)

    if assignee_filter == 'unassigned':
        where_clause += " AND assigned_to IS NULL"
    elif assignee_filter == 'me' and user_role in ['admin', 'it']:
        where_clause += " AND assigned_to = %s"
        params.append(username)

    if search_query:
        where_clause += " AND (ticket_code ILIKE %s OR title ILIKE %s OR created_by ILIKE %s)"
        params.extend([f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'])

    count_query = "SELECT COUNT(*) AS total, COALESCE(MAX(id), 0) AS max_id FROM tickets " + where_clause
    data_query = "SELECT * FROM tickets " + where_clause + " ORDER BY id DESC LIMIT %s OFFSET %s"

    cur.execute(count_query, tuple(params))
    count_row = cur.fetchone()
    total = count_row['total']
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages)
    offset = (page - 1) * PER_PAGE
    cur.execute(data_query, tuple(params) + (PER_PAGE, offset))
    tickets_list = cur.fetchall()

    latest_ticket_id = count_row['max_id']

    def _page_url(p):
        return url_for('tickets.index', page=p if p != 1 else None,
                       status=status_filter or None,
                       assignee=assignee_filter if assignee_filter != 'all' else None,
                       q=search_query or None)

    page_urls = [(p, _page_url(p)) for p in range(max(1, page - 3), min(total_pages, page + 3) + 1)]
    pagination = {
        'page': page, 'total_pages': total_pages, 'total': total,
        'prev_url': _page_url(page - 1) if page > 1 else None,
        'next_url': _page_url(page + 1) if page < total_pages else None,
        'page_urls': page_urls,
    }

    open_ticket_ids = [t['id'] for t in tickets_list if t['status'] not in ['Resolved', 'Closed']]
    responded_ids = set()
    if open_ticket_ids:
        cur.execute("""
            SELECT DISTINCT ta.ticket_id
            FROM ticket_activities ta
            JOIN users u ON ta.actor = u.username
            WHERE ta.ticket_id = ANY(%s)
              AND ta.type IN ('comment', 'status', 'assignment')
              AND u.role IN ('admin', 'it');
        """, (open_ticket_ids,))
        responded_ids = {row['ticket_id'] for row in cur.fetchall()}

    now = datetime.now()
    for t in tickets_list:
        has_resp = (t['id'] in responded_ids) if t['status'] not in ['Resolved', 'Closed'] else False
        t['sla'] = compute_sla(t, has_response=has_resp, now=now)

    cur.close()
    conn.close()

    return render_template('tickets/index.html', tickets=tickets_list, status_filter=status_filter, assignee_filter=assignee_filter, search_query=search_query, active_page='tickets', latest_ticket_id=latest_ticket_id, pagination=pagination)

# --- BUAT TIKET BARU ---
@tickets_bp.route('/add', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'it', 'user')
def add():
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        title = request.form.get('title')
        category = request.form.get('category')
        priority = request.form.get('priority')
        description = request.form.get('description')
        ticket_code = generate_ticket_code()

        created_by = session.get('username')
        user_dept = session.get('department', 'IT')

        try:
            cur.execute("""
                INSERT INTO tickets (ticket_code, title, category, priority, status, description, created_by, department)
                VALUES (%s, %s, %s, %s, 'Open', %s, %s, %s)
                RETURNING id;
            """, (ticket_code, title, category, priority, description, created_by, user_dept))
            ticket_row = cur.fetchone()
            new_ticket_id = ticket_row['id']
            cur.execute("""
                INSERT INTO ticket_activities (ticket_id, actor, type, content)
                VALUES (%s, %s, 'created', %s);
            """, (new_ticket_id, created_by, f"Ticket created by {created_by}"))
            conn.commit()
            cur.close()
            conn.close()

            files = request.files.getlist('attachments')
            handle_ticket_attachments(new_ticket_id, files, created_by)

            created_ticket = {
                'id': new_ticket_id,
                'ticket_code': ticket_code,
                'title': title,
                'status': 'Open',
                'priority': priority,
                'assigned_to': None,
            }
            enqueue_webhook('ticket.created', created_ticket, created_by)

            flash(f"Tiket {ticket_code} berhasil dibuat!", "success")
            return redirect(url_for('tickets.index'))
        except Exception as e:
            conn.rollback()
            cur.close()
            conn.close()
            return f"Error creating ticket: {e}"

    cur.execute("SELECT * FROM ticket_categories ORDER BY name ASC;")
    categories = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('tickets/add.html', categories=categories, active_page='tickets')

@tickets_bp.route('/api/new-count')
@login_required
@roles_required('admin', 'it')
def new_count():
    try:
        since_id = int(request.args.get('since_id', 0))
    except (ValueError, TypeError):
        since_id = 0

    status_filter = request.args.get('status', '')
    assignee_filter = request.args.get('assignee', 'all').strip()
    search_query = request.args.get('q', '')
    user_role = session.get('role', 'guest')
    username = session.get('username')

    conn = get_db_connection()
    cur = conn.cursor()

    query = "SELECT COUNT(*) AS new_count, COALESCE(MAX(id), 0) AS latest_id FROM tickets WHERE is_deleted = FALSE AND id > %s"
    params = [since_id]

    if status_filter:
        query += " AND status = %s"
        params.append(status_filter)

    if assignee_filter == 'unassigned':
        query += " AND assigned_to IS NULL"
    elif assignee_filter == 'me' and user_role in ['admin', 'it']:
        query += " AND assigned_to = %s"
        params.append(username)

    if search_query:
        query += " AND (ticket_code ILIKE %s OR title ILIKE %s OR created_by ILIKE %s)"
        params.extend([f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'])

    cur.execute(query, tuple(params))
    row = cur.fetchone()
    cur.close()
    conn.close()

    new_count_val = row['new_count'] if row else 0
    latest_id_val = row['latest_id'] if row else 0

    return jsonify({"new_count": new_count_val, "latest_id": latest_id_val})

# --- DETAIL TIKET ---
@tickets_bp.route('/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'it', 'user', 'guest')
def detail(ticket_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM tickets WHERE id = %s AND is_deleted = FALSE;", (ticket_id,))
    ticket = cur.fetchone()

    if not ticket:
        cur.close()
        conn.close()
        return "Tiket tidak ditemukan", 404

    user_role = session.get('role')
    username = session.get('username')

    # Proteksi: Regular User dan Guest hanya bisa melihat tiket miliknya sendiri
    if user_role in ('user', 'guest') and ticket['created_by'] != username:
        cur.close()
        conn.close()
        flash("Akses ditolak! Anda tidak berhak melihat tiket pengguna lain.", "danger")
        return redirect(url_for('tickets.index'))

    if request.method == 'POST':
        action = request.form.get('action', 'update_status')

        if ticket['status'] in ['Resolved', 'Closed'] and action in ['comment', 'upload_attachment']:
            cur.close()
            conn.close()
            flash("Tiket sudah terkunci!", "danger")
            return redirect(url_for('tickets.detail', ticket_id=ticket_id))

        if action == 'comment':
            if user_role == 'guest':
                cur.close()
                conn.close()
                flash("Akses ditolak! Guest tidak diizinkan menambahkan komentar.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            comment_text = request.form.get('comment', '').strip()
            if comment_text:
                cur.execute("""
                    INSERT INTO ticket_activities (ticket_id, actor, type, content)
                    VALUES (%s, %s, 'comment', %s);
                """, (ticket_id, username, comment_text))
                conn.commit()
                flash("Komentar berhasil ditambahkan!", "success")

            cur.close()
            conn.close()
            return redirect(url_for('tickets.detail', ticket_id=ticket_id))

        elif action == 'upload_attachment':
            if user_role == 'guest':
                cur.close()
                conn.close()
                flash("Akses ditolak! Guest tidak diizinkan mengunggah lampiran.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            files = request.files.getlist('attachments')
            valid_files = [f for f in files if f and f.filename and f.filename.strip()]
            if not valid_files:
                flash("Pilih setidaknya satu file untuk diunggah.", "warning")
            else:
                success = handle_ticket_attachments(ticket_id, valid_files, username)
                if success:
                    flash("Lampiran berhasil diunggah!", "success")

            cur.close()
            conn.close()
            return redirect(url_for('tickets.detail', ticket_id=ticket_id))

        elif action == 'submit_rating':
            if user_role == 'guest':
                cur.close()
                conn.close()
                flash("Guest tidak diizinkan memberi penilaian.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            if ticket['status'] not in ['Resolved', 'Closed']:
                cur.close()
                conn.close()
                flash("Penilaian hanya dapat diberikan untuk tiket yang sudah selesai.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            if ticket['created_by'] != username:
                cur.close()
                conn.close()
                flash("Hanya pelapor tiket yang dapat memberikan penilaian.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            try:
                rating_val = int(request.form.get('rating', ''))
                if rating_val < 1 or rating_val > 5:
                    raise ValueError()
            except (ValueError, TypeError):
                cur.close()
                conn.close()
                flash("Penilaian harus berupa angka antara 1 dan 5.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            comment_val = request.form.get('comment', '').strip()
            if len(comment_val) > 1000:
                cur.close()
                conn.close()
                flash("Komentar penilaian tidak boleh lebih dari 1000 karakter.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            cur.execute("""
                INSERT INTO ticket_ratings (ticket_id, rating, comment, rater)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (ticket_id) DO UPDATE SET
                    rating = EXCLUDED.rating,
                    comment = EXCLUDED.comment,
                    rater = EXCLUDED.rater,
                    updated_at = CURRENT_TIMESTAMP;
            """, (ticket_id, rating_val, comment_val if comment_val else None, username))

            cur.execute("""
                INSERT INTO ticket_activities (ticket_id, actor, type, content)
                VALUES (%s, %s, 'rating', %s);
            """, (ticket_id, username, f"Rating {rating_val}/5 by {username}" + (f": {comment_val}" if comment_val else "")))

            conn.commit()
            cur.close()
            conn.close()
            flash("Penilaian berhasil disimpan!", "success")
            return redirect(url_for('tickets.detail', ticket_id=ticket_id))

        elif action == 'reopen':
            if user_role == 'guest':
                cur.close()
                conn.close()
                flash("Guest tidak diizinkan membuka ulang tiket.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            if ticket['status'] not in ['Resolved', 'Closed']:
                cur.close()
                conn.close()
                flash("Hanya tiket yang sudah selesai yang dapat dibuka ulang.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            if username != ticket['created_by'] and user_role not in ['admin', 'it']:
                cur.close()
                conn.close()
                flash("Akses ditolak! Anda tidak memiliki izin untuk membuka ulang tiket ini.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            reason = request.form.get('reopen_reason', '').strip()
            if len(reason) > 500:
                cur.close()
                conn.close()
                flash("Alasan buka ulang tiket tidak boleh lebih dari 500 karakter.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            cur.execute("""
                UPDATE tickets
                SET status = 'Open', resolved_by = NULL, resolved_at = NULL, resolution_note = NULL
                WHERE id = %s;
            """, (ticket_id,))

            content = f"Ticket reopened by {username}" + (f" (Reason: {reason})" if reason else "")
            cur.execute("""
                INSERT INTO ticket_activities (ticket_id, actor, type, content)
                VALUES (%s, %s, 'status', %s);
            """, (ticket_id, username, content))

            conn.commit()
            cur.close()
            conn.close()

            flash("Tiket berhasil dibuka ulang!", "success")
            updated_ticket = dict(ticket)
            updated_ticket.update({
                'status': 'Open',
                'resolved_by': None,
                'resolved_at': None,
                'resolution_note': None
            })
            enqueue_webhook('ticket.status_changed', updated_ticket, username)
            return redirect(url_for('tickets.detail', ticket_id=ticket_id))

        elif action == 'link':
            if user_role not in ['admin', 'it']:
                cur.close()
                conn.close()
                flash("Akses ditolak! Hanya Tim IT & Admin yang dapat menambah relasi tiket.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            relation_type = request.form.get('relation_type', '').strip()
            if relation_type not in ['duplicate', 'related']:
                cur.close()
                conn.close()
                flash("Jenis relasi tidak valid.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            target_code = request.form.get('target_code', '').strip().upper()
            if not target_code:
                cur.close()
                conn.close()
                flash("Kode tiket target tidak boleh kosong.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            cur.execute("SELECT id, ticket_code, status FROM tickets WHERE ticket_code = %s;", (target_code,))
            target = cur.fetchone()
            if not target:
                cur.close()
                conn.close()
                flash("Tiket target tidak ditemukan.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            if target['id'] == ticket_id:
                cur.close()
                conn.close()
                flash("Tiket tidak dapat dihubungkan ke dirinya sendiri.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            cur.execute("""
                SELECT id FROM ticket_relationships
                WHERE (ticket_a_id = %s AND ticket_b_id = %s)
                   OR (ticket_a_id = %s AND ticket_b_id = %s);
            """, (ticket_id, target['id'], target['id'], ticket_id))
            if cur.fetchone():
                cur.close()
                conn.close()
                flash("Relasi antar tiket ini sudah ada.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            cur.execute("""
                INSERT INTO ticket_relationships (ticket_a_id, ticket_b_id, relation_type, created_by)
                VALUES (%s, %s, %s, %s);
            """, (ticket_id, target['id'], relation_type, username))

            auto_close = (relation_type == 'duplicate' and ticket['status'] in ['Open', 'In Progress'])
            resolution_note = None
            if auto_close:
                resolution_note = f"Duplikat dari {target_code}"
                cur.execute("""
                    UPDATE tickets
                    SET status = 'Closed', resolved_by = %s, resolved_at = CURRENT_TIMESTAMP, resolution_note = %s
                    WHERE id = %s;
                """, (username, resolution_note, ticket_id))
                cur.execute("""
                    INSERT INTO ticket_activities (ticket_id, actor, type, content)
                    VALUES (%s, %s, 'status', %s);
                """, (ticket_id, username, f"Ticket marked as duplicate of {target_code} by {username}"))
            else:
                cur.execute("""
                    INSERT INTO ticket_activities (ticket_id, actor, type, content)
                    VALUES (%s, %s, 'relation', %s);
                """, (ticket_id, username, f"Ticket linked to {target_code} as {relation_type} by {username}"))

            if relation_type == 'duplicate':
                target_activity = f"Ticket {ticket['ticket_code']} marked as duplicate of this ticket by {username}"
            else:
                target_activity = f"Ticket {ticket['ticket_code']} linked as related by {username}"
            cur.execute("""
                INSERT INTO ticket_activities (ticket_id, actor, type, content)
                VALUES (%s, %s, 'relation', %s);
            """, (target['id'], username, target_activity))

            conn.commit()
            cur.close()
            conn.close()

            if auto_close:
                updated_ticket = dict(ticket)
                updated_ticket['status'] = 'Closed'
                updated_ticket['resolved_by'] = username
                updated_ticket['resolution_note'] = resolution_note
                enqueue_webhook('ticket.status_changed', updated_ticket, username)
                flash("Tiket ditandai sebagai duplikat dan ditutup.", "success")
            else:
                flash("Relasi tiket berhasil ditambahkan!", "success")

            return redirect(url_for('tickets.detail', ticket_id=ticket_id))

        elif action == 'unlink':
            if user_role not in ['admin', 'it']:
                cur.close()
                conn.close()
                flash("Akses ditolak! Hanya Tim IT & Admin yang dapat menghapus relasi tiket.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            relation_id = request.form.get('relation_id')
            cur.execute("""
                SELECT * FROM ticket_relationships
                WHERE id = %s AND (ticket_a_id = %s OR ticket_b_id = %s);
            """, (relation_id, ticket_id, ticket_id))
            rel = cur.fetchone()
            if not rel:
                cur.close()
                conn.close()
                flash("Relasi tidak ditemukan.", "danger")
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            other_id = rel['ticket_b_id'] if rel['ticket_a_id'] == ticket_id else rel['ticket_a_id']
            cur.execute("SELECT ticket_code FROM tickets WHERE id = %s;", (other_id,))
            other_ticket = cur.fetchone()
            other_code = other_ticket['ticket_code'] if other_ticket else f"#{other_id}"

            cur.execute("DELETE FROM ticket_relationships WHERE id = %s;", (relation_id,))

            cur.execute("""
                INSERT INTO ticket_activities (ticket_id, actor, type, content)
                VALUES (%s, %s, 'relation', %s);
            """, (ticket_id, username, f"Ticket unlinked from {other_code} by {username}"))

            cur.execute("""
                INSERT INTO ticket_activities (ticket_id, actor, type, content)
                VALUES (%s, %s, 'relation', %s);
            """, (other_id, username, f"Ticket {ticket['ticket_code']} unlinked by {username}"))

            conn.commit()
            cur.close()
            conn.close()
            flash("Relasi tiket berhasil dihapus.", "success")
            return redirect(url_for('tickets.detail', ticket_id=ticket_id))

        else:
            if user_role not in ['admin', 'it']:
                flash("Akses ditolak! Hanya Tim IT & Admin yang dapat memperbarui status tiket.", "danger")
                cur.close()
                conn.close()
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            if ticket['status'] in ['Resolved', 'Closed']:
                flash("Tiket ini telah selesai/ditutup dan tidak dapat diubah lagi!", "danger")
                cur.close()
                conn.close()
                return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            new_status = request.form.get('status')
            resolution_note = request.form.get('resolution_note', '').strip()
            user_now = session.get('username')
            raw_assigned = request.form.get('assigned_to', '').strip()
            assigned_to = raw_assigned if raw_assigned and raw_assigned.lower() != 'unassigned' else None

            if assigned_to:
                cur.execute("SELECT id FROM users WHERE username = %s AND role IN ('admin', 'it') AND is_deleted = FALSE;", (assigned_to,))
                if not cur.fetchone():
                    cur.close()
                    conn.close()
                    flash("Assignee tidak valid!", "danger")
                    return redirect(url_for('tickets.detail', ticket_id=ticket_id))

            old_status = ticket['status']
            old_assigned_to = ticket['assigned_to']

            status_changed = bool(new_status and new_status != old_status)
            assigned_changed = bool(assigned_to != old_assigned_to)

            if status_changed:
                cur.execute("""
                    INSERT INTO ticket_activities (ticket_id, actor, type, content)
                    VALUES (%s, %s, 'status', %s);
                """, (ticket_id, user_now, f"Status changed from {old_status} to {new_status}"))

            if assigned_changed:
                assign_content = f"Assigned to {assigned_to}" if assigned_to else "Assignment cleared (Unassigned)"
                cur.execute("""
                    INSERT INTO ticket_activities (ticket_id, actor, type, content)
                    VALUES (%s, %s, 'assignment', %s);
                """, (ticket_id, user_now, assign_content))

            if (not status_changed and not assigned_changed) and (resolution_note != (ticket['resolution_note'] or '')):
                cur.execute("""
                    INSERT INTO ticket_activities (ticket_id, actor, type, content)
                    VALUES (%s, %s, 'note', %s);
                """, (ticket_id, user_now, f"Resolution note updated by {user_now}"))

            if new_status in ['Resolved', 'Closed']:
                cur.execute("""
                    UPDATE tickets
                    SET status = %s, resolution_note = %s, resolved_by = %s, resolved_at = CURRENT_TIMESTAMP,
                        assigned_to = %s
                    WHERE id = %s;
                """, (new_status, resolution_note, user_now, assigned_to, ticket_id))
            else:
                cur.execute("""
                    UPDATE tickets
                    SET status = %s, resolution_note = %s, assigned_to = %s
                    WHERE id = %s;
                """, (new_status, resolution_note, assigned_to, ticket_id))

            conn.commit()
            cur.close()
            conn.close()

            updated_ticket = dict(ticket)
            if new_status:
                updated_ticket['status'] = new_status
            updated_ticket['assigned_to'] = assigned_to

            if status_changed:
                enqueue_webhook('ticket.status_changed', updated_ticket, user_now)

            if assigned_changed:
                enqueue_webhook('ticket.assigned', updated_ticket, user_now)

            flash("Status dan laporan penyelesaian tiket berhasil diperbarui!", "success")
            return redirect(url_for('tickets.detail', ticket_id=ticket_id))

    assignees = []
    if user_role in ['admin', 'it']:
        cur.execute("SELECT username FROM users WHERE role IN ('admin', 'it') AND is_deleted = FALSE ORDER BY username ASC;")
        assignees = cur.fetchall()

    cur.execute("""
        SELECT ta.*, u.role as actor_role
        FROM ticket_activities ta
        LEFT JOIN users u ON ta.actor = u.username
        WHERE ta.ticket_id = %s
        ORDER BY ta.created_at DESC, ta.id DESC;
    """, (ticket_id,))
    activities = cur.fetchall()
    last_updated = activities[0]['created_at'] if activities else ticket['created_at']

    cur.execute("""
        SELECT * FROM ticket_attachments
        WHERE ticket_id = %s
        ORDER BY created_at ASC, id ASC;
    """, (ticket_id,))
    attachments = cur.fetchall()
    for att in attachments:
        att['formatted_size'] = format_file_size(att['size_bytes'])

    ticket['sla'] = compute_sla(ticket, activities=activities)

    cur.execute("SELECT * FROM ticket_ratings WHERE ticket_id = %s;", (ticket_id,))
    rating = cur.fetchone()

    related_articles = []
    if ticket.get('category'):
        cur.execute("""
            SELECT id, title, category FROM kb_articles
            WHERE status = 'published' AND category = %s
            ORDER BY created_at DESC LIMIT 5;
        """, (ticket['category'],))
        related_articles = cur.fetchall()

    canned_templates = []
    canned_templates_json = {}
    if user_role in ['admin', 'it']:
        cur.execute("SELECT id, title, content FROM canned_responses ORDER BY title ASC;")
        canned_templates = cur.fetchall()
        canned_templates_json = {str(t['id']): t['content'] for t in canned_templates}

    cur.execute("""
        SELECT r.id, r.relation_type, r.ticket_a_id, r.ticket_b_id,
               t.id AS other_id, t.ticket_code AS other_code,
               t.title AS other_title, t.status AS other_status
        FROM ticket_relationships r
        JOIN tickets t ON t.id = CASE WHEN r.ticket_a_id = %s
            THEN r.ticket_b_id ELSE r.ticket_a_id END
        WHERE r.ticket_a_id = %s OR r.ticket_b_id = %s
        ORDER BY r.created_at DESC;
    """, (ticket_id, ticket_id, ticket_id))
    relations = cur.fetchall()

    cur.close()
    conn.close()
    return render_template('tickets/detail.html', ticket=ticket, assignees=assignees, activities=activities, attachments=attachments, related_articles=related_articles, rating=rating, canned_templates=canned_templates, canned_templates_json=canned_templates_json, relations=relations, last_updated=last_updated, active_page='tickets')

# --- UNDUH LAMPIRAN TIKET ---
@tickets_bp.route('/<int:ticket_id>/attachments/<int:att_id>/download')
@login_required
@roles_required('admin', 'it', 'user', 'guest')
def download_attachment(ticket_id, att_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM tickets WHERE id = %s AND is_deleted = FALSE;", (ticket_id,))
    ticket = cur.fetchone()

    if not ticket:
        cur.close()
        conn.close()
        return "Tiket tidak ditemukan", 404

    user_role = session.get('role')
    username = session.get('username')

    # Proteksi: Regular User dan Guest hanya bisa melihat tiket miliknya sendiri
    if user_role in ('user', 'guest') and ticket['created_by'] != username:
        cur.close()
        conn.close()
        flash("Akses ditolak! Anda tidak berhak melihat tiket pengguna lain.", "danger")
        return redirect(url_for('tickets.index'))

    cur.execute("SELECT * FROM ticket_attachments WHERE id = %s AND ticket_id = %s;", (att_id, ticket_id))
    attachment = cur.fetchone()
    cur.close()
    conn.close()

    if not attachment:
        return "Lampiran tidak ditemukan", 404

    upload_folder = get_upload_folder()
    file_path = os.path.join(upload_folder, attachment['stored_filename'])

    if not os.path.isfile(file_path):
        return "File tidak ditemukan di server", 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name=attachment['original_filename'],
        mimetype=attachment['mime_type']
    )

# --- KELOLA KATEGORI (KHUSUS ADMIN) ---
@tickets_bp.route('/categories', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def manage_categories():
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        new_category = request.form.get('category_name', '').strip()
        if new_category:
            try:
                cur.execute("INSERT INTO ticket_categories (name) VALUES (%s);", (new_category,))
                conn.commit()
                flash(f"Kategori '{new_category}' berhasil ditambahkan!", "success")
            except Exception as e:
                conn.rollback()
                flash("Kategori sudah ada atau terjadi kesalahan.", "danger")

    cur.execute("SELECT * FROM ticket_categories ORDER BY name ASC;")
    categories = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('tickets/categories.html', categories=categories, active_page='tickets')

@tickets_bp.route('/categories/delete/<int:category_id>', methods=['POST'])
@login_required
@roles_required('admin')
def delete_category(category_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM ticket_categories WHERE id = %s;", (category_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Kategori berhasil dihapus.", "success")
    return redirect(url_for('tickets.manage_categories'))

# --- KELOLA TEMPLATE RESPON (KHUSUS ADMIN & IT) ---
@tickets_bp.route('/canned-responses', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'it')
def manage_canned_responses():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM ticket_categories ORDER BY name ASC;")
        categories = cur.fetchall()
        valid_category_names = {c['name'] for c in categories}

        form_data = None
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            category_raw = request.form.get('category', '').strip()

            if not title:
                flash("Judul template tidak boleh kosong.", "danger")
            elif len(title) > 255:
                flash("Judul template tidak boleh lebih dari 255 karakter.", "danger")
            elif not content:
                flash("Konten template tidak boleh kosong.", "danger")
            elif category_raw and category_raw not in valid_category_names:
                flash("Kategori tidak valid.", "danger")
            else:
                category = category_raw if category_raw else 'Umum'
                author = session.get('username')
                cur.execute("""
                    INSERT INTO canned_responses (title, content, category, author)
                    VALUES (%s, %s, %s, %s);
                """, (title, content, category, author))
                conn.commit()
                flash("Template respon berhasil ditambahkan!", "success")
                return redirect(url_for('tickets.manage_canned_responses'))

            form_data = {'title': title, 'content': content, 'category': category_raw}

        cur.execute("SELECT * FROM canned_responses ORDER BY title ASC;")
        templates = cur.fetchall()
        return render_template(
            'tickets/canned_responses.html',
            templates=templates,
            categories=categories,
            form_data=form_data,
            active_page='tickets'
        )
    finally:
        cur.close()
        conn.close()

@tickets_bp.route('/canned-responses/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'it')
def edit_canned_response(template_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM canned_responses WHERE id = %s;", (template_id,))
        template_item = cur.fetchone()
        if not template_item:
            abort(404)

        cur.execute("SELECT name FROM ticket_categories ORDER BY name ASC;")
        categories = cur.fetchall()
        valid_category_names = {c['name'] for c in categories}

        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            category_raw = request.form.get('category', '').strip()

            if not title:
                flash("Judul template tidak boleh kosong.", "danger")
            elif len(title) > 255:
                flash("Judul template tidak boleh lebih dari 255 karakter.", "danger")
            elif not content:
                flash("Konten template tidak boleh kosong.", "danger")
            elif category_raw and category_raw not in valid_category_names:
                flash("Kategori tidak valid.", "danger")
            else:
                category = category_raw if category_raw else 'Umum'
                cur.execute("""
                    UPDATE canned_responses
                    SET title = %s, content = %s, category = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s;
                """, (title, content, category, template_id))
                conn.commit()
                flash("Template respon berhasil diperbarui!", "success")
                return redirect(url_for('tickets.manage_canned_responses'))

            template_item['title'] = title
            template_item['content'] = content
            template_item['category'] = category_raw

        return render_template(
            'tickets/canned_response_edit.html',
            template_item=template_item,
            categories=categories,
            active_page='tickets'
        )
    finally:
        cur.close()
        conn.close()

@tickets_bp.route('/canned-responses/<int:template_id>/delete', methods=['POST'])
@login_required
@roles_required('admin', 'it')
def delete_canned_response(template_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM canned_responses WHERE id = %s;", (template_id,))
        template_item = cur.fetchone()
        if not template_item:
            abort(404)

        cur.execute("DELETE FROM canned_responses WHERE id = %s;", (template_id,))
        conn.commit()
        flash("Template respon berhasil dihapus.", "success")
        return redirect(url_for('tickets.manage_canned_responses'))
    finally:
        cur.close()
        conn.close()

# --- HAPUS PERMANEN (KHUSUS ADMIN BER-PASSWORD) ---
@tickets_bp.route('/delete-permanent/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def delete_permanent(ticket_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM tickets WHERE id = %s;", (ticket_id,))
    ticket = cur.fetchone()

    if not ticket:
        cur.close()
        conn.close()
        return "Tiket tidak ditemukan", 404

    error = None
    if request.method == 'POST':
        input_password = request.form.get('confirm_password', '')
        user_id = session.get('user_id')

        cur.execute("SELECT password_hash FROM users WHERE id = %s AND is_deleted = FALSE;", (user_id,))
        admin_data = cur.fetchone()

        if not admin_data or not check_password_hash(admin_data['password_hash'], input_password):
            error = "Password Admin salah! Penghapusan permanen dibatalkan."
        else:
            cur.execute("DELETE FROM ticket_activities WHERE ticket_id = %s;", (ticket_id,))

            cur.execute("SELECT stored_filename FROM ticket_attachments WHERE ticket_id = %s;", (ticket_id,))
            attachments = cur.fetchall()
            upload_folder = get_upload_folder()
            for att in attachments:
                stored_name = att.get('stored_filename')
                if stored_name:
                    file_path = os.path.join(upload_folder, stored_name)
                    if os.path.isfile(file_path):
                        try:
                            os.remove(file_path)
                        except OSError:
                            pass

            cur.execute("DELETE FROM ticket_attachments WHERE ticket_id = %s;", (ticket_id,))
            cur.execute("DELETE FROM ticket_ratings WHERE ticket_id = %s;", (ticket_id,))
            cur.execute("DELETE FROM ticket_relationships WHERE ticket_a_id = %s OR ticket_b_id = %s;", (ticket_id, ticket_id))
            cur.execute("DELETE FROM tickets WHERE id = %s;", (ticket_id,))
            conn.commit()
            cur.close()
            conn.close()
            flash(f"Tiket {ticket['ticket_code']} berhasil dihapus permanen.", "danger")
            return redirect(url_for('tickets.index'))

    cur.close()
    conn.close()
    return render_template('tickets/delete_permanent.html', ticket=ticket, error=error, active_page='tickets')
