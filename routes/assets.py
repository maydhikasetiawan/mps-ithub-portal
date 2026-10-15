from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from routes.auth import login_required, roles_required
from database.db import get_db_connection
from datetime import datetime

assets_bp = Blueprint('assets', __name__, url_prefix='/assets')

ALLOWED_STATUSES = ['Procurement', 'Active', 'Under Repair', 'Retired']

def calculate_age(created_at):
    if not created_at:
        return "-"
    now = datetime.now()
    diff = now - created_at
    days = diff.days

    if days < 1:
        return "Hari ini"
    elif days < 30:
        return f"{days} Hari"
    elif days < 365:
        months = days // 30
        remaining_days = days % 30
        return f"{months} Bulan {remaining_days} Hari"
    else:
        years = days // 365
        remaining_months = (days % 365) // 30
        return f"{years} Tahun {remaining_months} Bulan"

# --- DAFTAR ASET AKTIF (IPAM) ---
@assets_bp.route('/')
@login_required
@roles_required('admin', 'it', 'guest')
def index():
    search_query = request.args.get('q', '')
    status_filter = request.args.get('status', '').strip()
    if status_filter not in ALLOWED_STATUSES:
        status_filter = ''

    conn = get_db_connection()
    cur = conn.cursor()

    query = "SELECT * FROM assets WHERE is_deleted = FALSE"
    params = []

    if status_filter:
        query += " AND status = %s"
        params.append(status_filter)

    if search_query:
        query += " AND (name ILIKE %s OR asset_tag ILIKE %s OR ip_address ILIKE %s OR location ILIKE %s)"
        params.extend([f'%{search_query}%', f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'])

    query += " ORDER BY id DESC;"
    cur.execute(query, tuple(params))

    assets_list = cur.fetchall()
    cur.close()
    conn.close()

    for asset in assets_list:
        asset['age'] = calculate_age(asset['created_at'])

    return render_template('assets/index.html', assets=assets_list, search_query=search_query, status_filter=status_filter, active_page='assets')

# --- TAMBAH ASET BARU ---
@assets_bp.route('/add', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'it')
def add():
    if request.method == 'POST':
        asset_tag = request.form.get('asset_tag', '').strip()
        name = request.form.get('name', '').strip()
        category = request.form.get('category')
        ip_address = request.form.get('ip_address', '').strip()
        mac_address = request.form.get('mac_address', '').strip()
        status = request.form.get('status')
        location = request.form.get('location', '').strip()
        notes = request.form.get('notes', '').strip()
        user_now = session.get('username')

        if status not in ALLOWED_STATUSES:
            flash("Status tidak valid.", "danger")
            return render_template('assets/add.html', active_page='assets')

        conn = get_db_connection()
        cur = conn.cursor()

        # VALIDASI: Cek apakah Asset Tag sudah digunakan
        cur.execute("SELECT id FROM assets WHERE asset_tag = %s;", (asset_tag,))
        existing_asset = cur.fetchone()
        if existing_asset:
            cur.close()
            conn.close()
            flash(f"Gagal! Asset Tag '{asset_tag}' sudah terdaftar di sistem. Gunakan Tag lain.", "danger")
            return render_template('assets/add.html', active_page='assets')

        try:
            cur.execute("""
                INSERT INTO assets (asset_tag, name, category, ip_address, mac_address, status, location, notes, updated_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (asset_tag, name, category, ip_address, mac_address, status, location, notes, user_now))
            conn.commit()
            cur.close()
            conn.close()
            flash(f"Aset '{name}' ({asset_tag}) berhasil ditambahkan!", "success")
            return redirect(url_for('assets.index'))
        except Exception as e:
            conn.rollback()
            cur.close()
            conn.close()
            flash(f"Terjadi kesalahan saat menyimpan data: {e}", "danger")
            return render_template('assets/add.html', active_page='assets')

    return render_template('assets/add.html', active_page='assets')

# --- DETAIL ASET ---
@assets_bp.route('/<int:asset_id>')
@login_required
@roles_required('admin', 'it', 'guest')
def detail(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM assets WHERE id = %s;", (asset_id,))
    asset = cur.fetchone()
    cur.close()
    conn.close()

    if not asset:
        return "Asset tidak ditemukan", 404

    asset['age'] = calculate_age(asset['created_at'])
    return render_template('assets/detail.html', asset=asset, active_page='assets')

# --- EDIT ASET ---
@assets_bp.route('/edit/<int:asset_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'it')
def edit(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        ip_address = request.form.get('ip_address')
        mac_address = request.form.get('mac_address')
        status = request.form.get('status')
        location = request.form.get('location')
        notes = request.form.get('notes')
        user_now = session.get('username')

        if status not in ALLOWED_STATUSES:
            cur.execute("SELECT * FROM assets WHERE id = %s AND is_deleted = FALSE;", (asset_id,))
            asset = cur.fetchone()
            cur.close()
            conn.close()
            if not asset:
                return "Asset tidak ditemukan atau sudah dihapus", 404
            flash("Status tidak valid.", "danger")
            return render_template('assets/edit.html', asset=asset, active_page='assets')

        try:
            cur.execute("""
                UPDATE assets
                SET ip_address = %s, mac_address = %s, status = %s, location = %s, notes = %s,
                    updated_at = CURRENT_TIMESTAMP, updated_by = %s
                WHERE id = %s;
            """, (ip_address, mac_address, status, location, notes, user_now, asset_id))
            conn.commit()
            cur.close()
            conn.close()
            flash("Detail aset berhasil diperbarui!", "success")
            return redirect(url_for('assets.index'))
        except Exception as e:
            conn.rollback()
            cur.close()
            conn.close()
            return f"Error updating asset: {e}"

    cur.execute("SELECT * FROM assets WHERE id = %s AND is_deleted = FALSE;", (asset_id,))
    asset = cur.fetchone()
    cur.close()
    conn.close()

    if not asset:
        return "Asset tidak ditemukan atau sudah dihapus", 404

    return render_template('assets/edit.html', asset=asset, active_page='assets')

# --- SOFT DELETE (HAPUS KE RIWAYAT) ---
@assets_bp.route('/delete/<int:asset_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'it')
def delete(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        reason = request.form.get('delete_reason')
        user_now = session.get('username')

        cur.execute("""
            UPDATE assets
            SET is_deleted = TRUE,
                deleted_at = CURRENT_TIMESTAMP,
                deleted_by = %s,
                delete_reason = %s
            WHERE id = %s;
        """, (user_now, reason, asset_id))
        conn.commit()
        cur.close()
        conn.close()
        flash("Aset berhasil dipindahkan ke Riwayat Aset Terhapus.", "success")
        return redirect(url_for('assets.index'))

    cur.execute("SELECT * FROM assets WHERE id = %s AND is_deleted = FALSE;", (asset_id,))
    asset = cur.fetchone()
    cur.close()
    conn.close()

    if not asset:
        return "Asset tidak ditemukan", 404

    return render_template('assets/delete_confirm.html', asset=asset, active_page='assets')

# --- RESTORE ASET ---
@assets_bp.route('/restore/<int:asset_id>', methods=['POST'])
@login_required
@roles_required('admin', 'it')
def restore(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM assets WHERE id = %s AND is_deleted = TRUE;", (asset_id,))
    asset = cur.fetchone()

    if not asset:
        cur.close()
        conn.close()
        return "Asset terhapus tidak ditemukan", 404

    user_now = session.get('username')
    cur.execute("""
        UPDATE assets
        SET is_deleted = FALSE,
            deleted_at = NULL,
            deleted_by = NULL,
            delete_reason = NULL,
            updated_at = CURRENT_TIMESTAMP,
            updated_by = %s
        WHERE id = %s;
    """, (user_now, asset_id))
    conn.commit()
    cur.close()
    conn.close()

    flash(f"Aset '{asset['name']}' ({asset['asset_tag']}) berhasil dikembalikan ke inventaris.", "success")
    return redirect(url_for('assets.deleted_history'))

# --- RIWAYAT ASET TERHAPUS ---
@assets_bp.route('/deleted-history')
@login_required
@roles_required('admin', 'it', 'guest')
def deleted_history():
    search_query = request.args.get('q', '')
    conn = get_db_connection()
    cur = conn.cursor()

    if search_query:
        cur.execute("""
            SELECT * FROM assets
            WHERE is_deleted = TRUE
              AND (name ILIKE %s OR asset_tag ILIKE %s OR ip_address ILIKE %s OR delete_reason ILIKE %s)
            ORDER BY deleted_at DESC;
        """, (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
    else:
        cur.execute("SELECT * FROM assets WHERE is_deleted = TRUE ORDER BY deleted_at DESC;")

    deleted_assets = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('assets/deleted_history.html', assets=deleted_assets, search_query=search_query, active_page='assets')

# --- DETAIL ASET TERHAPUS ---
@assets_bp.route('/deleted-detail/<int:asset_id>')
@login_required
@roles_required('admin', 'it', 'guest')
def deleted_detail(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM assets WHERE id = %s AND is_deleted = TRUE;", (asset_id,))
    asset = cur.fetchone()
    cur.close()
    conn.close()

    if not asset:
        return "Asset terhapus tidak ditemukan", 404

    asset['age'] = calculate_age(asset['created_at'])
    return render_template('assets/deleted_detail.html', asset=asset, active_page='assets')

# --- HARD DELETE (HAPUS PERMANEN BERLAPIS KHUSUS ADMIN) ---
@assets_bp.route('/hard-delete/<int:asset_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def hard_delete(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM assets WHERE id = %s AND is_deleted = TRUE;", (asset_id,))
    asset = cur.fetchone()

    if not asset:
        cur.close()
        conn.close()
        return "Asset tidak ditemukan di riwayat terhapus", 404

    error = None
    if request.method == 'POST':
        input_name = request.form.get('confirm_name', '').strip()
        input_password = request.form.get('confirm_password', '')
        user_id = session.get('user_id')

        cur.execute("SELECT password_hash FROM users WHERE id = %s;", (user_id,))
        user_data = cur.fetchone()

        if input_name != asset['name']:
            error = f"Nama perangkat tidak sesuai! Anda memasukkan '{input_name}', seharusnya '{asset['name']}'."
        elif not user_data or not check_password_hash(user_data['password_hash'], input_password):
            error = "Password Anda salah! Hapus permanen dibatalkan."
        else:
            cur.execute("DELETE FROM assets WHERE id = %s;", (asset_id,))
            conn.commit()
            cur.close()
            conn.close()
            flash("Aset telah dihapus secara permanen dari database.", "danger")
            return redirect(url_for('assets.deleted_history'))

    cur.close()
    conn.close()
    return render_template('assets/hard_delete_confirm.html', asset=asset, error=error, active_page='assets')
