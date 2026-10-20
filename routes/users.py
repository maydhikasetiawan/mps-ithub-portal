from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from routes.auth import login_required, roles_required
from database.db import get_db_connection

users_bp = Blueprint('users', __name__, url_prefix='/users')

def log_user_activity(cur, user_id, actor, activity_type, content):
    cur.execute("""
        INSERT INTO user_activities (user_id, actor, type, content)
        VALUES (%s, %s, %s, %s);
    """, (user_id, actor, activity_type, content))

# --- DAFTAR USER (KHUSUS SUPER ADMIN) ---
@users_bp.route('/')
@login_required
@roles_required('admin')
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, email, role, department, created_at FROM users WHERE is_deleted = FALSE ORDER BY id ASC;")
    users_list = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('users/index.html', users=users_list, active_page='users')

# --- TAMBAH USER BARU ---
@users_bp.route('/add', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def add():
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password')
        role = request.form.get('role')
        department = request.form.get('department')

        try:
            password_hash = generate_password_hash(password)
            cur.execute("""
                INSERT INTO users (username, email, password_hash, role, department)
                VALUES (%s, %s, %s, %s, %s);
            """, (username, email, password_hash, role, department))
            log_user_activity(cur, None, session.get('username'), 'user_created',
                f"User '{username}' created with role '{role}', department '{department or '-'}'.")
            conn.commit()
            cur.close()
            conn.close()
            flash(f"User '{username}' berhasil ditambahkan!", "success")
            return redirect(url_for('users.index'))
        except Exception as e:
            conn.rollback()
            flash("Username atau Email sudah terdaftar!", "danger")

    cur.execute("SELECT * FROM departments ORDER BY name ASC;")
    departments = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('users/add.html', departments=departments, active_page='users')

# --- HAPUS USER (SOFT DELETE) ---
@users_bp.route('/delete/<int:user_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def delete(user_id):
    if user_id == session.get('user_id'):
        flash("Anda tidak bisa menghapus akun Anda sendiri yang sedang login!", "danger")
        return redirect(url_for('users.index'))

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        reason = request.form.get('delete_reason')
        reason_val = reason.strip() if reason and reason.strip() else None
        user_now = session.get('username')

        cur.execute("SELECT username FROM users WHERE id = %s;", (user_id,))
        target = cur.fetchone()

        cur.execute("""
            UPDATE users
            SET is_deleted = TRUE,
                deleted_at = CURRENT_TIMESTAMP,
                deleted_by = %s,
                delete_reason = %s
            WHERE id = %s;
        """, (user_now, reason_val, user_id))
        if target:
            log_user_activity(cur, user_id, user_now, 'user_soft_deleted',
                f"User '{target['username']}' soft-deleted by '{user_now}'." + (f" Reason: {reason_val}" if reason_val else ""))
        conn.commit()
        cur.close()
        conn.close()
        flash("User berhasil dipindahkan ke Riwayat User Terhapus.", "success")
        return redirect(url_for('users.index'))

    cur.execute("SELECT * FROM users WHERE id = %s AND is_deleted = FALSE;", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        return "User tidak ditemukan", 404

    return render_template('users/delete_confirm.html', user=user, active_page='users')

# --- RIWAYAT USER TERHAPUS ---
@users_bp.route('/deleted-history')
@login_required
@roles_required('admin')
def deleted_history():
    search_query = request.args.get('q', '').strip()
    conn = get_db_connection()
    cur = conn.cursor()

    if search_query:
        cur.execute("""
            SELECT * FROM users
            WHERE is_deleted = TRUE
              AND (username ILIKE %s OR email ILIKE %s OR delete_reason ILIKE %s)
            ORDER BY deleted_at DESC;
        """, (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
    else:
        cur.execute("SELECT * FROM users WHERE is_deleted = TRUE ORDER BY deleted_at DESC;")

    deleted_users = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('users/deleted_history.html', users=deleted_users, search_query=search_query, active_page='users')

# --- DETAIL USER TERHAPUS ---
@users_bp.route('/deleted-detail/<int:user_id>')
@login_required
@roles_required('admin')
def deleted_detail(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s AND is_deleted = TRUE;", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        return "User terhapus tidak ditemukan", 404

    return render_template('users/deleted_detail.html', user=user, active_page='users')

# --- RESTORE USER ---
@users_bp.route('/restore/<int:user_id>', methods=['POST'])
@login_required
@roles_required('admin')
def restore(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s AND is_deleted = TRUE;", (user_id,))
    user = cur.fetchone()

    if not user:
        cur.close()
        conn.close()
        return "User terhapus tidak ditemukan", 404

    cur.execute("""
        UPDATE users
        SET is_deleted = FALSE,
            deleted_at = NULL,
            deleted_by = NULL,
            delete_reason = NULL
        WHERE id = %s;
    """, (user_id,))
    log_user_activity(cur, user_id, session.get('username'), 'user_restored',
        f"User '{user['username']}' restored by '{session.get('username')}'.")
    conn.commit()
    cur.close()
    conn.close()

    flash(f"User '{user['username']}' berhasil dikembalikan.", "success")
    return redirect(url_for('users.deleted_history'))

# --- HARD DELETE (HAPUS PERMANEN) ---
@users_bp.route('/hard-delete/<int:user_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def hard_delete(user_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE id = %s AND is_deleted = TRUE;", (user_id,))
    user = cur.fetchone()

    if not user:
        cur.close()
        conn.close()
        return "User tidak ditemukan di riwayat terhapus", 404

    error = None
    if request.method == 'POST':
        input_username = request.form.get('confirm_username', '').strip()
        input_password = request.form.get('confirm_password', '')
        admin_id = session.get('user_id')

        cur.execute("SELECT password_hash FROM users WHERE id = %s AND is_deleted = FALSE;", (admin_id,))
        admin_data = cur.fetchone()

        if input_username != user['username']:
            error = f"Username tidak sesuai! Anda memasukkan '{input_username}', seharusnya '{user['username']}'."
        elif not admin_data or not check_password_hash(admin_data['password_hash'], input_password):
            error = "Password Anda salah! Hapus permanen dibatalkan."
        else:
            cur.execute("DELETE FROM users WHERE id = %s;", (user_id,))
            log_user_activity(cur, user_id, session.get('username'), 'user_hard_deleted',
                f"User '{user['username']}' permanently deleted by '{session.get('username')}'.")
            conn.commit()
            cur.close()
            conn.close()
            flash(f"User '{user['username']}' telah dihapus secara permanen dari database.", "danger")
            return redirect(url_for('users.deleted_history'))

    cur.close()
    conn.close()
    return render_template('users/hard_delete_confirm.html', user=user, error=error, active_page='users')

# --- MANAJEMEN DEPARTEMEN MODULAR ---
@users_bp.route('/departments', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def departments():
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        dept_name = request.form.get('department_name', '').strip()
        if dept_name:
            cur.execute("SELECT id FROM departments WHERE LOWER(name) = LOWER(%s);", (dept_name,))
            if cur.fetchone():
                flash(f"Departemen '{dept_name}' sudah ada!", "danger")
            else:
                cur.execute("INSERT INTO departments (name) VALUES (%s);", (dept_name,))
                log_user_activity(cur, None, session.get('username'), 'department_created',
                    f"Department '{dept_name}' created by '{session.get('username')}'.")
                conn.commit()
                flash(f"Departemen '{dept_name}' berhasil ditambahkan!", "success")

    cur.execute("SELECT * FROM departments ORDER BY name ASC;")
    dept_list = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('users/departments.html', departments=dept_list, active_page='users')

@users_bp.route('/departments/delete/<int:dept_id>', methods=['POST'])
@login_required
@roles_required('admin')
def delete_department(dept_id):
    conn = get_db_connection()
    cur = conn.cursor()

    # Ambil nama departemen sebelum dihapus
    cur.execute("SELECT name FROM departments WHERE id = %s;", (dept_id,))
    dept = cur.fetchone()

    if dept:
        # Cek apakah ada user yang masih terdaftar di departemen ini
        cur.execute("SELECT COUNT(*) as count FROM users WHERE department = %s AND is_deleted = FALSE;", (dept['name'],))
        user_count = cur.fetchone()['count']

        if user_count > 0:
            flash(f"Gagal menghapus! Masih ada {user_count} user di departemen '{dept['name']}'. Pindahkan user terlebih dahulu.", "danger")
        else:
            cur.execute("DELETE FROM departments WHERE id = %s;", (dept_id,))
            log_user_activity(cur, None, session.get('username'), 'department_deleted',
                f"Department '{dept['name']}' deleted by '{session.get('username')}'.")
            conn.commit()
            flash(f"Departemen '{dept['name']}' berhasil dihapus.", "success")

    cur.close()
    conn.close()
    return redirect(url_for('users.departments'))

# --- EDIT USER (KHUSUS ADMIN) ---
@users_bp.route('/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def edit(user_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE id = %s AND is_deleted = FALSE;", (user_id,))
    target_user = cur.fetchone()

    if not target_user:
        cur.close()
        conn.close()
        flash("User tidak ditemukan!", "danger")
        return redirect(url_for('users.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        role = request.form.get('role')
        department = request.form.get('department')
        new_password = request.form.get('new_password', '').strip()

        try:
            if new_password:
                # Jika password diisi oleh Admin -> Reset Password & Set Flag Wajib Ganti
                pwd_hash = generate_password_hash(new_password)
                cur.execute("""
                    UPDATE users
                    SET email = %s, role = %s, department = %s, password_hash = %s, must_change_password = TRUE
                    WHERE id = %s;
                """, (email, role, department, pwd_hash, user_id))
                flash(f"Data dan password user '{target_user['username']}' berhasil diperbarui! User diwajibkan ganti password saat login berikutnya.", "success")
            else:
                cur.execute("""
                    UPDATE users
                    SET email = %s, role = %s, department = %s
                    WHERE id = %s;
                """, (email, role, department, user_id))
                flash(f"Data user '{target_user['username']}' berhasil diperbarui!", "success")

            if role != target_user['role']:
                log_user_activity(cur, user_id, session.get('username'), 'role_changed',
                    f"User '{target_user['username']}' role changed from '{target_user['role']}' to '{role}' by '{session.get('username')}'.")
            if new_password:
                log_user_activity(cur, user_id, session.get('username'), 'password_reset',
                    f"Password reset for user '{target_user['username']}' by '{session.get('username')}'.")
            if email != target_user['email']:
                log_user_activity(cur, user_id, session.get('username'), 'email_changed',
                    f"User '{target_user['username']}' email changed from '{target_user['email']}' to '{email}' by '{session.get('username')}'.")
            if department != target_user['department']:
                log_user_activity(cur, user_id, session.get('username'), 'department_changed',
                    f"User '{target_user['username']}' department changed from '{target_user['department']}' to '{department}' by '{session.get('username')}'.")

            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for('users.index'))

        except Exception as e:
            conn.rollback()
            flash(f"Error updating user: {e}", "danger")

    cur.execute("SELECT * FROM departments ORDER BY name ASC;")
    departments = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('users/edit.html', user=target_user, departments=departments, active_page='users')

# --- GANTI PASSWORD MANDIRI (UNTUK SEMUA USER) ---
@users_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if session.get('role') == 'guest':
        flash("Akun guest tidak dapat mengganti password.", "danger")
        return redirect(url_for('dashboard.index'))
    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if new_password != confirm_password:
            flash("Konfirmasi password baru tidak cocok!", "danger")
            return render_template('users/change_password.html')

        user_id = session.get('user_id')
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT password_hash FROM users WHERE id = %s AND is_deleted = FALSE;", (user_id,))
        user_data = cur.fetchone()

        if not user_data or not check_password_hash(user_data['password_hash'], old_password):
            cur.close()
            conn.close()
            flash("Password lama Anda salah!", "danger")
            return render_template('users/change_password.html')

        new_hash = generate_password_hash(new_password)
        cur.execute("""
            UPDATE users
            SET password_hash = %s, must_change_password = FALSE
            WHERE id = %s;
        """, (new_hash, user_id))
        log_user_activity(cur, user_id, session.get('username'), 'password_changed',
            f"User '{session.get('username')}' changed their own password.")
        conn.commit()
        cur.close()
        conn.close()

        # Update Session
        session['must_change_password'] = False
        flash("Password Anda berhasil diperbarui!", "success")
        return redirect(url_for('dashboard.index'))

    return render_template('users/change_password.html')
