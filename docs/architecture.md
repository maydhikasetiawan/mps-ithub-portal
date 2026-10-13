# Arsitektur Sistem MPS-ITHub Portal

Dokumen ini menjelaskan rancangan arsitektur, tumpukan teknologi (*technology stack*), tata letak repositori, modul rute, skema basis data, model otentikasi & hak akses, serta alur *deployment pipeline*.

---

## 1. Tumpukan Teknologi (Tech Stack)

- **Backend Framework**: Python 3.11, Flask 3.0.2, Werkzeug 3.0.1
- **Template Engine & UI**: Jinja2 dengan Vanilla Custom CSS (tanpa framework CSS eksternal seperti Bootstrap/Tailwind)
- **Database & Migration**: PostgreSQL, driver `psycopg2-binary` 2.9.9 (`RealDictCursor`), skema migrasi menggunakan Alembic 1.13.1
- **Containerization**: Docker (base image `python:3.11-slim`)
- **CI/CD & Infrastruktur**: GitHub Actions, GitHub Container Registry (`ghcr.io`), AWS EC2 via SSH (`appleboy/ssh-action`)

---

## 2. Struktur Repositori (Repo Layout)

```text
my-web-app/
├── .github/workflows/    # Definisi workflow CI/CD GitHub Actions (deploy.yml)
├── database/             # Modul koneksi PostgreSQL dan inisialisasi tabel dasar (db.py)
├── docs/                 # Dokumentasi teknis aplikasi
├── migrations/           # Konfigurasi Alembic dan skrip migrasi versi skema
│   └── versions/         # Berkas revisi migrasi (001_add_missing_schema_objects.py)
├── routes/               # Modular Flask Blueprints per domain fitur
├── templates/            # Template HTML Jinja2 (antarmuka pengguna)
│   ├── assets/           # Template manajemen inventaris aset & IPAM
│   ├── reports/          # Template laporan & ekspor data
│   ├── tickets/          # Template helpdesk tiket & kategori
│   ├── uptime/           # Template pemantauan uptime server/layanan
│   └── users/            # Template manajemen user & departemen
├── .env.example          # Template variabel lingkungan
├── alembic.ini           # Berkas konfigurasi logging & metadata Alembic
├── app.py                # Titik masuk utama aplikasi Flask & registrasi rute
├── Dockerfile            # Konfigurasi container image Python
└── requirements.txt      # Daftar dependensi Python
```

---

## 3. Rincian Modul Aplikasi (Modules & Key Routes)

Aplikasi dibangun berbasis modul Blueprint Flask:

### a. `auth` (`routes/auth.py`, URL prefix: root)
- **Tujuan**: Menangani autentikasi sesi, pembatasan brute force (*rate limiting* 5 kali gagal per jendela 15 menit per IP/username), dan dekorator izin akses.
- **Rute Utama**:
  - `GET, POST /login` — Halaman dan pemrosesan autentikasi login pengguna.
  - `GET /logout` — Menghapus sesi dan mengarahkan kembali ke halaman login.

### b. `dashboard` (`routes/dashboard.py`, URL prefix: root)
- **Tujuan**: Menampilkan statistik ringkasan operasional secara waktu nyata.
- **Rute Utama**:
  - `GET /` & `GET /dashboard` — Agregasi total aset aktif, jumlah tiket terbuka/dalam pengerjaan, dan persentase ketersediaan layanan (*uptime percentage*).

### c. `assets` (`routes/assets.py`, URL prefix: `/assets`)
- **Tujuan**: Manajemen inventaris aset TI dan IP Address Management (IPAM). Mendukung pencatatan aset, penghitungan usia perangkat, validasi keunikan tag aset, soft delete beralasan, pemulihan (*restore*), serta penghapusan permanen khusus admin dengan verifikasi ganda.
- **Rute Utama**:
  - `GET /assets/` — Daftar aset aktif dengan filter pencarian.
  - `GET, POST /assets/add` — Formulir penambahan aset baru.
  - `GET /assets/<int:asset_id>` — Detail spesifikasi dan histori aset.
  - `GET, POST /assets/edit/<int:asset_id>` — Pembaruan informasi perangkat.
  - `GET, POST /assets/delete/<int:asset_id>` — Soft delete aset ke riwayat terhapus.
  - `POST /assets/restore/<int:asset_id>` — Mengembalikan aset terhapus ke status aktif.
  - `GET /assets/deleted-history` — Riwayat seluruh aset yang berstatus terhapus.
  - `GET /assets/deleted-detail/<int:asset_id>` — Detail informasi aset terhapus.
  - `GET, POST /assets/hard-delete/<int:asset_id>` — Hapus permanen dari basis data (konfirmasi nama dan kata sandi admin).

### d. `tickets` (`routes/tickets.py`, URL prefix: `/tickets`)
- **Tujuan**: Layanan helpdesk/service desk internal. Pembuatan kode tiket otomatis (`TCK-YYYYMMDD-XXX`), filter status, penyelesaian masalah (*resolution note*), penugasan staf, penambahan komentar, serta pencatatan linimasa aktivitas terpadu dan manajemen kategori dinamis.
- **Rute Utama**:
  - `GET /tickets/` — Daftar tiket (pengguna biasa hanya melihat tiket miliknya; mendukung filter status dan parameter `assignee`: `all`, `unassigned`, `me`).
  - `GET, POST /tickets/add` — Pembuatan laporan masalah baru beserta pencatatan otomatis aktivitas `created`.
  - `GET, POST /tickets/<int:ticket_id>` — Detail tiket beserta linimasa aktivitas; penanganan POST terbagi: penambahan komentar (`action=comment`, admin/it/user pada tiketnya) dan pembaruan status/assignee (`action=update_status`, admin/it) dengan auto-logging riwayat status dan penugasan.
  - `GET, POST /tickets/categories` — Manajemen kategori tiket (Admin).
  - `GET /tickets/categories/delete/<int:category_id>` — Hapus kategori tiket (Admin).
  - `GET, POST /tickets/delete-permanent/<int:ticket_id>` — Hapus permanen tiket (Admin).

### e. `uptime` (`routes/uptime.py`, URL prefix: `/uptime`)
- **Tujuan**: Pemantauan ketersediaan target server/layanan melalui pengecekan TCP port atau HTTP request beserta pencatatan latensi (ms).
- **Rute Utama**:
  - `GET /uptime/` — Dasbor status monitor dan ringkasan target aktif/mati.
  - `GET, POST /uptime/add` — Menambahkan target baru dengan uji kesehatan instan.
  - `GET /uptime/check/<int:monitor_id>` — Uji ulang kesehatan satu target.
  - `GET /uptime/check-all` — Uji ulang seluruh target sekaligus.
  - `GET /uptime/delete/<int:monitor_id>` — Menghapus target monitor.

### f. `users` (`routes/users.py`, URL prefix: `/users`)
- **Tujuan**: Administrasi pengguna dan struktur departemen organisasi, reset password administratif dengan flag wajib ganti, serta antarmuka penggantian kata sandi mandiri.
- **Rute Utama**:
  - `GET /users/` — Daftar pengguna terdaftar.
  - `GET, POST /users/add` — Pendaftaran akun pengguna baru.
  - `GET, POST /users/edit/<int:user_id>` — Pembaruan data pengguna dan opsi reset kata sandi.
  - `GET /users/delete/<int:user_id>` — Penghapusan akun pengguna (proteksi akun sendiri).
  - `GET, POST /users/departments` — Pengelolaan daftar departemen.
  - `GET /users/departments/delete/<int:dept_id>` — Hapus departemen (proteksi bila masih ada user terkait).
  - `GET, POST /users/change-password` — Penggantian kata sandi mandiri bagi pengguna aktif.

### g. `reports` (`routes/reports.py`, URL prefix: `/reports`)
- **Tujuan**: Penyediaan laporan analitis dan ekspor data tabular ke berkas CSV dengan format UTF-8-SIG untuk kompatibilitas Microsoft Excel.
- **Rute Utama**:
  - `GET /reports/` — Antarmuka pemilihan filter laporan.
  - `GET /reports/export/assets` — Unduh data aset dalam bentuk CSV.
  - `GET /reports/export/tickets` — Unduh data tiket helpdesk dalam bentuk CSV.

### h. `health` (`app.py`, URL prefix: root)
- **Tujuan**: Endpoint pemantauan kondisi service tanpa autentikasi.
- **Rute**:
  - `GET /health` — Mengembalikan JSON `{"status": "healthy"}` dengan status HTTP 200.

---

## 4. Skema Basis Data (Database Schema)

Skema dibentuk melalui inisialisasi awal pada `database/db.py` dan disempurnakan oleh migrasi Alembic (`migrations/versions/001_add_missing_schema_objects.py`):

1. **`users`**
   - Kolom: `id` (PK, Serial), `username` (VARCHAR 50, Unique), `email` (VARCHAR 100, Unique), `password_hash` (TEXT), `role` (VARCHAR 20, default 'staff'), `department` (VARCHAR 50, default 'IT'), `must_change_password` (BOOLEAN, default FALSE), `created_at` (TIMESTAMP).
   - Data bawaan: akun `admin` (role admin) dan `guest` (role guest).
2. **`assets`**
   - Kolom: `id` (PK, Serial), `asset_tag` (VARCHAR 50, Unique), `name` (VARCHAR 100), `category` (VARCHAR 50), `ip_address` (VARCHAR 45), `mac_address` (VARCHAR 45), `status` (VARCHAR 20, default 'Active'), `location` (VARCHAR 100), `notes` (TEXT), `is_deleted` (BOOLEAN, default FALSE), `deleted_at` (TIMESTAMP), `deleted_by` (VARCHAR 50), `delete_reason` (TEXT), `created_at` (TIMESTAMP), `updated_at` (TIMESTAMP), `updated_by` (VARCHAR 50).
3. **`tickets`**
   - Kolom: `id` (PK, Serial), `ticket_code` (VARCHAR 20, Unique), `title` (VARCHAR 150), `category` (VARCHAR 50), `priority` (VARCHAR 20, default 'Medium'), `status` (VARCHAR 20, default 'Open'), `description` (TEXT), `created_by` (VARCHAR 50), `assigned_to` (VARCHAR 50), `department` (VARCHAR 50), `resolution_note` (TEXT), `resolved_by` (VARCHAR 50), `resolved_at` (TIMESTAMP), `is_deleted` (BOOLEAN, default FALSE), `deleted_at` (TIMESTAMP), `deleted_by` (VARCHAR 50), `delete_reason` (TEXT), `created_at` (TIMESTAMP).
4. **`ticket_categories`**
   - Kolom: `id` (PK, Serial), `name` (VARCHAR 50, Unique).
   - Data bawaan: 'Hardware', 'Network', 'Software', 'Server', 'Request'.
5. **`departments`**
   - Kolom: `id` (PK, Serial), `name` (VARCHAR 50, Unique).
6. **`monitors`**
   - Kolom: `id` (PK, Serial), `name` (VARCHAR 100), `target` (VARCHAR 255), `type` (VARCHAR 20, default 'PING'), `port` (INT), `status` (VARCHAR 20, default 'UNKNOWN'), `latency` (INT, default 0), `last_check` (TIMESTAMP), `created_at` (TIMESTAMP).
7. **`service_monitors`** *(Tabel cadangan/inisial di db.py)*
   - Kolom: `id` (PK, Serial), `service_name` (VARCHAR 100), `target_url` (VARCHAR 255), `last_status` (VARCHAR 20), `response_time_ms` (INT), `last_checked` (TIMESTAMP). Catatan: Modul aktif `uptime` menggunakan tabel `monitors`.
8. **`ticket_activities`**
   - Kolom: `id` (PK, Serial), `ticket_id` (INT, Not Null), `actor` (VARCHAR 50), `type` (VARCHAR 20), `content` (TEXT), `created_at` (TIMESTAMP).
   - Menyimpan seluruh linimasa peristiwa tiket: `'created'`, `'status'`, `'assignment'`, dan `'comment'`.

*Relasi Relasional*:
Hubungan antar-tabel dijaga secara logis di tingkat aplikasi:
- `tickets.created_by`, `tickets.assigned_to`, `tickets.resolved_by`, `assets.updated_by`, `assets.deleted_by` berelasi logis ke `users.username`.
- `ticket_activities.ticket_id` berelasi logis ke `tickets.id`; `ticket_activities.actor` berelasi logis ke `users.username`.
- `users.department` dan `tickets.department` berelasi logis ke `departments.name`.
- `tickets.category` berelasi logis ke `ticket_categories.name`.

---

## 5. Autentikasi dan Manajemen Peran (Auth & Roles)

Sistem menggunakan session cookies terenkripsi (`SECRET_KEY`) dengan proteksi dua lapis:
1. `@login_required`: Memastikan pengunjung telah memiliki sesi aktif (`session['user_id']`).
2. `@roles_required(*allowed_roles)`: Memverifikasi nilai `session['role']` sesuai daftar peran yang diizinkan.

### Peran Pengguna:
- **`admin`**: Memiliki hak akses penuh mencakup manajemen pengguna, departemen, penghapusan permanen tiket dan aset, manajemen kategori, dan seluruh modul operasional.
- **`it`**: Tim teknis IT yang dapat mengelola aset (tambah/edit/soft delete/restore), memperbarui status tiket dan catatan solusi, serta mengelola target uptime monitor.
- **`user`**: Pengguna reguler internal yang hanya dapat melihat dan membuat tiket miliknya sendiri, serta melakukan penggantian kata sandi mandiri.
- **`guest`**: Akses baca (*read-only*) untuk meninjau dasbor, daftar aset, riwayat aset terhapus, tiket, dan uptime monitor tanpa izin modifikasi data.

Sistem juga menerapkan middleware `check_mandatory_password_change` pada `app.py` yang memaksa redirect ke `/users/change-password` jika nilai flag `session['must_change_password']` bernilai `True`.

---

## 6. Alur Pipeline Penerapan (Deploy Pipeline)

Otomatisasi pengiriman kode ke server produksi diatur melalui GitHub Actions pada file `.github/workflows/deploy.yml`:

1. **Trigger**: Event `push` ke branch utama (`main`).
2. **Job: build-and-push**:
   - Menjalankan runner `ubuntu-latest`.
   - Mengambil kode repositori (`actions/checkout@v4`).
   - Melakukan login ke GitHub Container Registry (`ghcr.io`) menggunakan akun `github.actor` dan `GITHUB_TOKEN`.
   - Membangun image Docker dan melakukan push dengan tag `ghcr.io/<repository>:latest`.
3. **Job: deploy-to-ec2**:
   - Berjalan setelah job `build-and-push` selesai dengan sukses (`needs: build-and-push`).
   - Membuka koneksi SSH ke server AWS EC2 via `appleboy/ssh-action@v1.0.3` menggunakan GitHub Secrets (`SSH_HOST`, `SSH_USERNAME`, `SSH_KEY`).
   - Mengeksekusi perintah shell pada server:
     - Melakukan `docker pull` image terbaru dari `ghcr.io`.
     - Menghentikan dan menghapus container lama `my-web-app`.
     - Menyiapkan jaringan docker `app-monitoring_default`.
     - Menjalankan container baru di port `5000:5000` dengan kebijakan restart otomatis (`--restart always`) serta menginjeksikan secrets: `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASS`, dan `SECRET_KEY`. Container memulai proses via `entrypoint.sh` yang menjalankan migrasi otomatis `alembic upgrade head` (bersifat idempoten — no-op bila sudah di head) sebelum menjalankan aplikasi Flask.
