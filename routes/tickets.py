from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from routes.auth import login_required, roles_required
from database.db import get_db_connection
from datetime import datetime

tickets_bp = Blueprint('tickets', __name__, url_prefix='/tickets')

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

            old_status = ticket['status']
            old_assigned_to = ticket['assigned_to']

            if new_status and new_status != old_status:
                cur.execute("""
                    INSERT INTO ticket_activities (ticket_id, actor, type, content)
                    VALUES (%s, %s, 'status', %s);
                """, (ticket_id, user_now, f"Status changed from {old_status} to {new_status}"))

            if assigned_to != old_assigned_to:
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
            flash("Status dan laporan penyelesaian tiket berhasil diperbarui!", "success")
            return redirect(url_for('tickets.detail', ticket_id=ticket_id))

    assignees = []
    if user_role in ['admin', 'it']:
        cur.execute("SELECT username FROM users WHERE role IN ('admin', 'it') ORDER BY username ASC;")
        assignees = cur.fetchall()

    cur.execute("SELECT * FROM ticket_activities WHERE ticket_id = %s ORDER BY created_at DESC, id DESC;", (ticket_id,))
    activities = cur.fetchall()

    cur.close()
    conn.close()
    return render_template('tickets/detail.html', ticket=ticket, assignees=assignees, activities=activities, active_page='tickets')

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
            cur.execute("DELETE FROM tickets WHERE id = %s;", (ticket_id,))
            conn.commit()
            cur.close()
            conn.close()
            flash(f"Tiket {ticket['ticket_code']} berhasil dihapus permanen.", "danger")
            return redirect(url_for('tickets.index'))

    cur.close()
    conn.close()
    return render_template('tickets/delete_permanent.html', ticket=ticket, error=error, active_page='tickets')
