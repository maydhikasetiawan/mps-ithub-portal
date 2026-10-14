from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash
from routes.auth import login_required, roles_required
from database.db import get_db_connection
from werkzeug.security import generate_password_hash, check_password_hash

users_bp = Blueprint('users', __name__, url_prefix='/users')

# --- DAFTAR USER (KHUSUS SUPER ADMIN) ---
@users_bp.route('/')
@login_required
@roles_required('admin')
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, email, role, department, created_at FROM users ORDER BY id ASC;")
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

# --- HAPUS USER ---
@users_bp.route('/delete/<int:user_id>', methods=['POST'])
@login_required
@roles_required('admin')
def delete(user_id):
    if user_id == session.get('user_id'):
        flash("Anda tidak bisa menghapus akun Anda sendiri yang sedang login!", "danger")
        return redirect(url_for('users.index'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = %s;", (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("User berhasil dihapus.", "success")
    return redirect(url_for('users.index'))

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
        cur.execute("SELECT COUNT(*) as count FROM users WHERE department = %s;", (dept['name'],))
        user_count = cur.fetchone()['count']

        if user_count > 0:
            flash(f"Gagal menghapus! Masih ada {user_count} user di departemen '{dept['name']}'. Pindahkan user terlebih dahulu.", "danger")
        else:
            cur.execute("DELETE FROM departments WHERE id = %s;", (dept_id,))
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

    cur.execute("SELECT * FROM users WHERE id = %s;", (user_id,))
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
        cur.execute("SELECT password_hash FROM users WHERE id = %s;", (user_id,))
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
        conn.commit()
        cur.close()
        conn.close()

        # Update Session
        session['must_change_password'] = False
        flash("Password Anda berhasil diperbarui!", "success")
        return redirect(url_for('dashboard.index'))

    return render_template('users/change_password.html')
