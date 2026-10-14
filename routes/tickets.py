from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file
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
from PIL import Image

tickets_bp = Blueprint('tickets', __name__, url_prefix='/tickets')

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

def send_webhook(event, ticket, actor):
    webhook_url = os.environ.get('WEBHOOK_URL', '').strip()
    if not webhook_url:
        return

    try:
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
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception:
        pass

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
        for f in valid_files:
            filename = f.filename or ''
            ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
            orig_name = secure_filename(filename) or f"file.{ext}"

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
    user_role = session.get('role', 'guest')
    username = session.get('username')

    conn = get_db_connection()
    cur = conn.cursor()

    query = "SELECT * FROM tickets WHERE is_deleted = FALSE"
    params = []

    # Regular User hanya melihat tiket miliknya sendiri
    if user_role == 'user':
        query += " AND created_by = %s"
        params.append(username)

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

    query += " ORDER BY id DESC;"
    cur.execute(query, tuple(params))
    tickets_list = cur.fetchall()

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

    return render_template('tickets/index.html', tickets=tickets_list, status_filter=status_filter, assignee_filter=assignee_filter, search_query=search_query, active_page='tickets')

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
            send_webhook('ticket.created', created_ticket, created_by)

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

    # Proteksi: Regular User hanya bisa melihat tiket miliknya sendiri
    if user_role == 'user' and ticket['created_by'] != username:
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
            send_webhook('ticket.status_changed', updated_ticket, username)
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
                cur.execute("SELECT id FROM users WHERE username = %s AND role IN ('admin', 'it');", (assigned_to,))
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
                send_webhook('ticket.status_changed', updated_ticket, user_now)

            if assigned_changed:
                send_webhook('ticket.assigned', updated_ticket, user_now)

            flash("Status dan laporan penyelesaian tiket berhasil diperbarui!", "success")
            return redirect(url_for('tickets.detail', ticket_id=ticket_id))

    assignees = []
    if user_role in ['admin', 'it']:
        cur.execute("SELECT username FROM users WHERE role IN ('admin', 'it') ORDER BY username ASC;")
        assignees = cur.fetchall()

    cur.execute("""
        SELECT ta.*, u.role as actor_role
        FROM ticket_activities ta
        LEFT JOIN users u ON ta.actor = u.username
        WHERE ta.ticket_id = %s
        ORDER BY ta.created_at DESC, ta.id DESC;
    """, (ticket_id,))
    activities = cur.fetchall()

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

    cur.close()
    conn.close()
    return render_template('tickets/detail.html', ticket=ticket, assignees=assignees, activities=activities, attachments=attachments, related_articles=related_articles, rating=rating, active_page='tickets')

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

    # Proteksi: Regular User hanya bisa melihat tiket miliknya sendiri
    if user_role == 'user' and ticket['created_by'] != username:
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

@tickets_bp.route('/categories/delete/<int:category_id>')
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

        cur.execute("SELECT password_hash FROM users WHERE id = %s;", (user_id,))
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
            cur.execute("DELETE FROM tickets WHERE id = %s;", (ticket_id,))
            conn.commit()
            cur.close()
            conn.close()
            flash(f"Tiket {ticket['ticket_code']} berhasil dihapus permanen.", "danger")
            return redirect(url_for('tickets.index'))

    cur.close()
    conn.close()
    return render_template('tickets/delete_permanent.html', ticket=ticket, error=error, active_page='tickets')
