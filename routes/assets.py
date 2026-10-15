from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from routes.auth import login_required, roles_required
from database.db import get_db_connection
from datetime import datetime, date

assets_bp = Blueprint('assets', __name__, url_prefix='/assets')

ALLOWED_STATUSES = ['Procurement', 'Active', 'Under Repair', 'Retired']

FIELD_LABELS = {
    'ip_address': 'IP Address',
    'mac_address': 'MAC Address',
    'status': 'Status',
    'assigned_to': 'Ditugaskan Kepada',
    'purchase_date': 'Tanggal Beli',
    'warranty_expiry': 'Garansi Habis',
    'no_warranty': 'Tanpa Garansi',
    'location': 'Lokasi',
    'notes': 'Catatan'
}

def render_audit_value(field, val):
    if val is None or val == '':
        return None
    if isinstance(val, (date, datetime)):
        return val.strftime('%Y-%m-%d')
    if isinstance(val, bool):
        return 'Ya' if val else 'Tidak'
    if field == 'no_warranty':
        return 'Ya' if val in (True, 'True', 'true', 1, '1') else 'Tidak'
    return str(val).strip() or None

def get_assignable_users():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT username FROM users WHERE role IN ('admin', 'it', 'user') ORDER BY username;")
    users = [row['username'] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return users

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

    assignable_users = get_assignable_users()
    assigned_filter = request.args.get('assigned', '').strip()
    if assigned_filter != 'unassigned' and assigned_filter not in assignable_users:
        assigned_filter = ''

    conn = get_db_connection()
    cur = conn.cursor()

    query = "SELECT * FROM assets WHERE is_deleted = FALSE"
    params = []

    if status_filter:
        query += " AND status = %s"
        params.append(status_filter)

    if assigned_filter == 'unassigned':
        query += " AND assigned_to IS NULL"
    elif assigned_filter:
        query += " AND assigned_to = %s"
        params.append(assigned_filter)

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

    return render_template('assets/index.html', assets=assets_list, search_query=search_query, status_filter=status_filter, assigned_filter=assigned_filter, users=assignable_users, active_page='assets')

# --- TAMBAH ASET BARU ---
@assets_bp.route('/add', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'it')
def add():
    assignable_users = get_assignable_users()

    if request.method == 'POST':
        asset_tag = request.form.get('asset_tag', '').strip()
        name = request.form.get('name', '').strip()
        category = request.form.get('category')
        ip_address = request.form.get('ip_address', '').strip()
        mac_address = request.form.get('mac_address', '').strip()
        status = request.form.get('status')
        assigned_to_raw = request.form.get('assigned_to', '').strip()
        no_warranty = (request.form.get('no_warranty') == '1')
        purchase_date_raw = request.form.get('purchase_date', '').strip()
        warranty_expiry_raw = request.form.get('warranty_expiry', '').strip()
        location = request.form.get('location', '').strip()
        notes = request.form.get('notes', '').strip()
        user_now = session.get('username')

        if status not in ALLOWED_STATUSES:
            flash("Status tidak valid.", "danger")
            return render_template('assets/add.html', users=assignable_users, active_page='assets')

        assigned_to = None
        if assigned_to_raw:
            if assigned_to_raw not in assignable_users:
                flash("Pengguna yang ditugaskan tidak valid.", "danger")
                return render_template('assets/add.html', users=assignable_users, active_page='assets')
            assigned_to = assigned_to_raw

        purchase_date = None
        if purchase_date_raw:
            try:
                purchase_date = datetime.strptime(purchase_date_raw, '%Y-%m-%d').date()
            except ValueError:
                flash("Tanggal beli tidak valid. Gunakan format YYYY-MM-DD.", "danger")
                return render_template('assets/add.html', users=assignable_users, active_page='assets')

        warranty_expiry = None
        if no_warranty:
            warranty_expiry = None
        else:
            if warranty_expiry_raw:
                try:
                    warranty_expiry = datetime.strptime(warranty_expiry_raw, '%Y-%m-%d').date()
                except ValueError:
                    flash("Tanggal garansi habis tidak valid. Gunakan format YYYY-MM-DD.", "danger")
                    return render_template('assets/add.html', users=assignable_users, active_page='assets')

            if purchase_date and warranty_expiry and warranty_expiry < purchase_date:
                flash("Tanggal garansi habis tidak boleh sebelum tanggal beli.", "danger")
                return render_template('assets/add.html', users=assignable_users, active_page='assets')

        conn = get_db_connection()
        cur = conn.cursor()

        # VALIDASI: Cek apakah Asset Tag sudah digunakan
        cur.execute("SELECT id FROM assets WHERE asset_tag = %s;", (asset_tag,))
        existing_asset = cur.fetchone()
        if existing_asset:
            cur.close()
            conn.close()
            flash(f"Gagal! Asset Tag '{asset_tag}' sudah terdaftar di sistem. Gunakan Tag lain.", "danger")
            return render_template('assets/add.html', users=assignable_users, active_page='assets')

        try:
            cur.execute("""
                INSERT INTO assets (asset_tag, name, category, ip_address, mac_address, status, assigned_to, purchase_date, warranty_expiry, no_warranty, location, notes, updated_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """, (asset_tag, name, category, ip_address, mac_address, status, assigned_to, purchase_date, warranty_expiry, no_warranty, location, notes, user_now))
            new_asset_id = cur.fetchone()['id']
            cur.execute("""
                INSERT INTO asset_activities (asset_id, actor, action, field_name, old_value, new_value)
                VALUES (%s, %s, 'created', NULL, NULL, NULL);
            """, (new_asset_id, user_now))
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
            return render_template('assets/add.html', users=assignable_users, active_page='assets')

    return render_template('assets/add.html', users=assignable_users, active_page='assets')

# --- DETAIL ASET ---
@assets_bp.route('/<int:asset_id>')
@login_required
@roles_required('admin', 'it', 'guest')
def detail(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM assets WHERE id = %s;", (asset_id,))
    asset = cur.fetchone()

    if not asset:
        cur.close()
        conn.close()
        return "Asset tidak ditemukan", 404

    cur.execute("SELECT * FROM asset_activities WHERE asset_id = %s ORDER BY created_at DESC, id DESC;", (asset_id,))
    activities = cur.fetchall()
    cur.close()
    conn.close()

    asset['age'] = calculate_age(asset['created_at'])

    warranty_status = "Tidak ada info garansi"
    days_remaining = None
    if asset['no_warranty']:
        warranty_status = "Tanpa Garansi"
    elif asset['warranty_expiry']:
        today = date.today()
        diff = (asset['warranty_expiry'] - today).days
        days_remaining = diff
        if diff > 0:
            warranty_status = f"Aktif — habis dalam {diff} hari"
        elif diff == 0:
            warranty_status = "Habis hari ini"
        else:
            warranty_status = f"Sudah habis — {abs(diff)} hari lalu"

    return render_template('assets/detail.html', asset=asset, activities=activities, FIELD_LABELS=FIELD_LABELS, warranty_status=warranty_status, days_remaining=days_remaining, active_page='assets')

# --- EDIT ASET ---
@assets_bp.route('/edit/<int:asset_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'it')
def edit(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()
    assignable_users = get_assignable_users()

    cur.execute("SELECT * FROM assets WHERE id = %s AND is_deleted = FALSE;", (asset_id,))
    old_asset = cur.fetchone()
    if not old_asset:
        cur.close()
        conn.close()
        return "Asset tidak ditemukan atau sudah dihapus", 404

    if request.method == 'POST':
        ip_address = request.form.get('ip_address')
        mac_address = request.form.get('mac_address')
        status = request.form.get('status')
        assigned_to_raw = request.form.get('assigned_to', '').strip()
        no_warranty = (request.form.get('no_warranty') == '1')
        purchase_date_raw = request.form.get('purchase_date', '').strip()
        warranty_expiry_raw = request.form.get('warranty_expiry', '').strip()
        location = request.form.get('location')
        notes = request.form.get('notes')
        user_now = session.get('username')

        if status not in ALLOWED_STATUSES:
            cur.close()
            conn.close()
            flash("Status tidak valid.", "danger")
            return render_template('assets/edit.html', asset=old_asset, users=assignable_users, active_page='assets')

        assigned_to = None
        if assigned_to_raw:
            if assigned_to_raw not in assignable_users:
                cur.close()
                conn.close()
                flash("Pengguna yang ditugaskan tidak valid.", "danger")
                return render_template('assets/edit.html', asset=old_asset, users=assignable_users, active_page='assets')
            assigned_to = assigned_to_raw

        purchase_date = None
        if purchase_date_raw:
            try:
                purchase_date = datetime.strptime(purchase_date_raw, '%Y-%m-%d').date()
            except ValueError:
                cur.close()
                conn.close()
                flash("Tanggal beli tidak valid. Gunakan format YYYY-MM-DD.", "danger")
                return render_template('assets/edit.html', asset=old_asset, users=assignable_users, active_page='assets')

        warranty_expiry = None
        if no_warranty:
            warranty_expiry = None
        else:
            if warranty_expiry_raw:
                try:
                    warranty_expiry = datetime.strptime(warranty_expiry_raw, '%Y-%m-%d').date()
                except ValueError:
                    cur.close()
                    conn.close()
                    flash("Tanggal garansi habis tidak valid. Gunakan format YYYY-MM-DD.", "danger")
                    return render_template('assets/edit.html', asset=old_asset, users=assignable_users, active_page='assets')

            if purchase_date and warranty_expiry and warranty_expiry < purchase_date:
                cur.close()
                conn.close()
                flash("Tanggal garansi habis tidak boleh sebelum tanggal beli.", "danger")
                return render_template('assets/edit.html', asset=old_asset, users=assignable_users, active_page='assets')

        try:
            cur.execute("""
                UPDATE assets
                SET ip_address = %s, mac_address = %s, status = %s, assigned_to = %s, purchase_date = %s, warranty_expiry = %s, no_warranty = %s, location = %s, notes = %s,
                    updated_at = CURRENT_TIMESTAMP, updated_by = %s
                WHERE id = %s;
            """, (ip_address, mac_address, status, assigned_to, purchase_date, warranty_expiry, no_warranty, location, notes, user_now, asset_id))

            new_values_map = {
                'ip_address': ip_address,
                'mac_address': mac_address,
                'status': status,
                'assigned_to': assigned_to,
                'purchase_date': purchase_date,
                'warranty_expiry': warranty_expiry,
                'no_warranty': no_warranty,
                'location': location,
                'notes': notes
            }

            for field_name in ['ip_address', 'mac_address', 'status', 'assigned_to', 'purchase_date', 'warranty_expiry', 'no_warranty', 'location', 'notes']:
                old_val_rendered = render_audit_value(field_name, old_asset.get(field_name))
                new_val_rendered = render_audit_value(field_name, new_values_map.get(field_name))
                if old_val_rendered != new_val_rendered:
                    cur.execute("""
                        INSERT INTO asset_activities (asset_id, actor, action, field_name, old_value, new_value)
                        VALUES (%s, %s, 'updated', %s, %s, %s);
                    """, (asset_id, user_now, field_name, old_val_rendered, new_val_rendered))

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

    cur.close()
    conn.close()
    return render_template('assets/edit.html', asset=old_asset, users=assignable_users, active_page='assets')

# --- SOFT DELETE (HAPUS KE RIWAYAT) ---
@assets_bp.route('/delete/<int:asset_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'it')
def delete(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        reason = request.form.get('delete_reason')
        reason_val = reason.strip() if reason and reason.strip() else None
        user_now = session.get('username')

        cur.execute("""
            UPDATE assets
            SET is_deleted = TRUE,
                deleted_at = CURRENT_TIMESTAMP,
                deleted_by = %s,
                delete_reason = %s
            WHERE id = %s;
        """, (user_now, reason, asset_id))
        cur.execute("""
            INSERT INTO asset_activities (asset_id, actor, action, field_name, old_value, new_value)
            VALUES (%s, %s, 'soft-deleted', NULL, NULL, %s);
        """, (asset_id, user_now, reason_val))
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
    cur.execute("""
        INSERT INTO asset_activities (asset_id, actor, action, field_name, old_value, new_value)
        VALUES (%s, %s, 'restored', NULL, NULL, NULL);
    """, (asset_id, user_now))
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
            cur.execute("DELETE FROM asset_activities WHERE asset_id = %s;", (asset_id,))
            cur.execute("DELETE FROM assets WHERE id = %s;", (asset_id,))
            conn.commit()
            cur.close()
            conn.close()
            flash("Aset telah dihapus secara permanen dari database.", "danger")
            return redirect(url_for('assets.deleted_history'))

    cur.close()
    conn.close()
    return render_template('assets/hard_delete_confirm.html', asset=asset, error=error, active_page='assets')
