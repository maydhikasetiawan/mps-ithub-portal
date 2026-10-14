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
- **Tujuan**: Layanan helpdesk/service desk internal. Pembuatan kode tiket otomatis (`TCK-YYYYMMDD-XXX`), filter status, penyelesaian masalah (*resolution note*), penugasan staf, penambahan komentar, kalkulasi Service Level Agreement (SLA) otomatis, serta pencatatan linimasa aktivitas terpadu dan manajemen kategori dinamis. Seluruh fitur tiket Fase 2 (penilaian kepuasan CSAT, buka ulang tiket/reopen, template respon/canned responses, dan relasi tiket/relationships) beroperasi di dalam blueprint ini melalui aksi dispatch pada `detail()` serta rute `/tickets/canned-responses*`.
- **Rute Utama**:
  - `GET /tickets/` — Daftar tiket (pengguna biasa hanya melihat tiket miliknya; mendukung filter status dan parameter `assignee`: `all`, `unassigned`, `me`; dilengkapi badge SLA).
  - `GET, POST /tickets/add` — Pembuatan laporan masalah baru beserta pencatatan otomatis aktivitas `created`.
  - `GET, POST /tickets/<int:ticket_id>` — Detail tiket beserta blok target/status SLA dan linimasa aktivitas; penanganan POST terbagi: penambahan komentar (`action=comment`, admin/it/user pada tiketnya), pembaruan status/assignee (`action=update_status`, admin/it), penilaian CSAT (`action=submit_rating`, reporter tiket), buka ulang tiket (`action=reopen`, reporter/admin/it), penautan relasi tiket (`action=link`, admin/it), dan pemutusan relasi (`action=unlink`, admin/it).
  - `GET, POST /tickets/categories` — Manajemen kategori tiket (Admin).
  - `GET /tickets/categories/delete/<int:category_id>` — Hapus kategori tiket (Admin).
  - `GET, POST /tickets/canned-responses` — Kelola pustaka template balasan tiket (Admin/IT).
  - `GET, POST /tickets/canned-responses/<int:template_id>/edit` — Edit template respon cepat (Admin/IT).
  - `POST /tickets/canned-responses/<int:template_id>/delete` — Hapus template respon cepat (Admin/IT).
  - `GET, POST /tickets/delete-permanent/<int:ticket_id>` — Hapus permanen tiket (Admin).
  - `GET /tickets/<int:ticket_id>/attachments/<int:att_id>/download` — Unduh berkas lampiran tiket dengan proteksi izin akses via `send_file`.
- **Aturan & State Machine SLA**:
  - **Konstanta Target (Jam Kalender)**: `Critical` (respon 1j, resolusi 4j), `High` (respon 2j, resolusi 8j), `Medium` (respon 4j, resolusi 24j), `Low` (respon 8j, resolusi 72j).
  - **Definisi Respon**: Entri aktivitas pertama bertipe `comment`, `status`, atau `assignment` oleh pengguna dengan role `admin` atau `it` (bergabung ke `users.role`). Entri `created` tidak dihitung sebagai respon.
  - **Definisi Resolusi**: Waktu `resolved_at` pada tiket berstatus `Resolved` atau `Closed` (atau `now - created_at` untuk tiket yang masih berjalan).
  - **State Machine**:
    - Tiket `Resolved`/`Closed`: Evaluasi `resolved_at - created_at` terhadap target resolusi → `SLA Terpenuhi` (`met`) jika dalam target, atau `SLA Terlewati` (`breached`) jika melebihi target.
    - Tiket `Open`/`In Progress` belum direspon: Evaluasi `now - created_at` terhadap target respon → `Mendekati SLA` (`approaching`) jika berjalan >= 80% target, `SLA Terlewati` (`breached`) jika > 100% target, tanpa badge jika < 80%.
    - Tiket `Open`/`In Progress` sudah direspon: Evaluasi `now - created_at` terhadap target resolusi dengan ambang batas 80% (`approaching`) dan 100% (`breached`).
- **Notifikasi Webhook**:
  - **Konfigurasi**: Membaca variabel lingkungan `WEBHOOK_URL` (melalui `os.environ.get`). Jika tidak diset atau bernilai kosong, pengiriman dilewati secara senyap (*silent skip*).
  - **Peristiwa (Events)**:
    - `ticket.created` — Dipicu setelah tiket baru berhasil dibuat dan transaksi basis data di-commit.
    - `ticket.status_changed` — Dipicu setelah status tiket diperbarui dan di-commit.
    - `ticket.assigned` — Dipicu setelah penugasan tiket diperbarui atau dikosongkan (*Unassigned*) dan di-commit.
    *(Catatan: Penambahan komentar tidak memicu webhook. Notifikasi email secara eksplisit ditunda / deferred).*
  - **Struktur Payload (JSON)**: Berisi kunci `event`, `ticket_code`, `ticket_id`, `title`, `status`, `priority`, `assigned_to` (username atau `null`), `actor` (username yang memicu aksi), `timestamp` (format ISO 8601 UTC), dan `url` (tautan tiket relatif, misal `/tickets/14`).
  - **Mekanisme Pengiriman**: HTTP POST sinkron berbasis pustaka standar Python `urllib` (tanpa dependensi eksternal). Bersifat *fail-open* dengan batas waktu (*timeout*) maksimal 5 detik di dalam penanganan `try/except: pass`; kegagalan pengiriman webhook tidak akan pernah menggagalkan operasi tiket.
- **Lampiran Berkas (File Attachments)**:
  - **Penyimpanan Berkas**: Disimpan di sistem berkas (*filesystem*) pada folder `uploads/` (dapat dikonfigurasi melalui variabel lingkungan `UPLOAD_FOLDER`, *default*: `uploads`). *Catatan Volume*: Perubahan kode ini tidak mempertahankan berkas saat container dibuat ulang; persistensi memerlukan volume mount permanen pada konfigurasi deployment server.
  - **Batas Unggahan**: Maksimal 2 berkas per tiket (total eksisting + baru), maksimal 5 MB per berkas. Ekstensi yang diizinkan (*allowlist*): `png`, `jpg`, `jpeg`, `gif`, `webp`, `pdf`, `txt`, `log`, `doc`, `docx`, `xls`, `xlsx`, `csv`. Ekstensi di luar daftar ditolak otomatis dengan pesan error.
  - **Aturan Kompresi**: Berkas gambar (`png`, `jpg`, `jpeg`, `webp`) otomatis diperkecil menggunakan Pillow (dimensi sisi terpanjang maksimal 1920px, hanya *downscale* tanpa memperbesar), dikonversi RGBA/palette ke RGB, dan disimpan dalam format JPEG kualitas 70 dengan ekstensi `.jpg`. Berkas `gif` dan non-gambar disimpan apa adanya (*as-is*).
  - **Keamanan Nama Berkas**: Nama berkas di filesystem menggunakan `uuid4().hex` acak untuk mencegah *path traversal*. Nama asli diamankan via `secure_filename` dan disimpan di basis data untuk tampilan/unduhan. Akses unduh divalidasi via rute `send_file` (bukan static path).

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

### i. `knowledge_base` (`routes/knowledge_base.py`, URL prefix: `/knowledge-base`)
- **Tujuan**: Modul basis pengetahuan solusi masalah teknis mandiri. Mendukung pencarian kata kunci, filter kategori, manajemen artikel draft dan published, serta referensi solusi artikel terkait pada tiket.
- **Rute Utama**:
  - `GET /knowledge-base/` — Daftar artikel solusi (pencarian kata kunci dan filter kategori).
  - `GET /knowledge-base/<int:article_id>` — Detail artikel pengetahuan (draft mengembalikan 404 bagi non-admin/IT).
  - `GET, POST /knowledge-base/add` — Penambahan artikel baru (Admin/IT).
  - `GET, POST /knowledge-base/edit/<int:article_id>` — Edit artikel pengetahuan (Admin/IT).
  - `POST /knowledge-base/delete/<int:article_id>` — Hapus artikel pengetahuan (Admin/IT).

---

## 4. Skema Basis Data (Database Schema)

Skema dibentuk melalui inisialisasi awal pada `database/db.py` dan disempurnakan oleh migrasi Alembic (`001–009`, dengan 009 sebagai pembersihan data yatim satu kali tanpa perubahan skema):

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
9. **`ticket_attachments`**
   - Kolom: `id` (PK, Serial), `ticket_id` (INT, Not Null), `stored_filename` (VARCHAR 255, Not Null), `original_filename` (VARCHAR 255, Not Null), `size_bytes` (INT, Not Null), `mime_type` (VARCHAR 100), `uploader` (VARCHAR 50), `created_at` (TIMESTAMP).
   - Menyimpan seluruh metadata berkas lampiran tiket.
10. **`kb_articles`** *(Migrasi 005)*
    - Kolom: `id` (PK, Serial), `title` (VARCHAR 255, Not Null), `category` (VARCHAR 100, Not Null), `content` (TEXT, Not Null), `tags` (VARCHAR 255), `status` (VARCHAR 20, default 'draft', check draft/published), `author` (VARCHAR 50), `created_at` (TIMESTAMP), `updated_at` (TIMESTAMP).
    - Tujuan: Menyimpan artikel panduan teknis dan solusi masalah Knowledge Base.
11. **`ticket_ratings`** *(Migrasi 006)*
    - Kolom: `id` (PK, Serial), `ticket_id` (INT, Not Null, Unique), `rating` (INT, Not Null, check 1-5), `comment` (TEXT), `rater` (VARCHAR 50), `created_at` (TIMESTAMP), `updated_at` (TIMESTAMP).
    - Tujuan: Menyimpan penilaian kepuasan layanan (CSAT) dari pelapor tiket.
12. **`canned_responses`** *(Migrasi 007)*
    - Kolom: `id` (PK, Serial), `title` (VARCHAR 255, Not Null), `content` (TEXT, Not Null), `category` (VARCHAR 100, default 'Umum'), `author` (VARCHAR 50), `created_at` (TIMESTAMP), `updated_at` (TIMESTAMP).
    - Tujuan: Menyimpan pustaka template balasan komentar Service Desk bagi Admin dan IT.
13. **`ticket_relationships`** *(Migrasi 008)*
    - Kolom: `id` (PK, Serial), `ticket_a_id` (INT, Not Null), `ticket_b_id` (INT, Not Null), `relation_type` (VARCHAR 20, Not Null: 'duplicate' / 'related'), `created_by` (VARCHAR 50), `created_at` (TIMESTAMP).
    - Tujuan: Menyimpan hubungan keterkaitan antar-tiket. Konvensi penyimpanan: `ticket_a_id` = tiket duplikat (sumber), `ticket_b_id` = tiket kanonikal (target). Keunikan pasangan kedua arah ditegakkan di level aplikasi tanpa constraint UNIQUE DB.

*Relasi Relasional*:
Hubungan antar-tabel dijaga secara logis di tingkat aplikasi:
- `tickets.created_by`, `tickets.assigned_to`, `tickets.resolved_by`, `assets.updated_by`, `assets.deleted_by` berelasi logis ke `users.username`.
- `ticket_activities.ticket_id`, `ticket_attachments.ticket_id`, dan `ticket_ratings.ticket_id` berelasi logis ke `tickets.id`.
- `ticket_relationships.ticket_a_id` dan `ticket_relationships.ticket_b_id` berelasi logis ke `tickets.id`.
- `ticket_activities.actor`, `ticket_attachments.uploader`, `ticket_ratings.rater`, `canned_responses.author`, `kb_articles.author`, dan `ticket_relationships.created_by` berelasi logis ke `users.username`.
- `users.department` dan `tickets.department` berelasi logis ke `departments.name`.
- `tickets.category`, `kb_articles.category`, dan `canned_responses.category` berelasi logis ke `ticket_categories.name`.
- Penghapusan permanen tiket (`delete_permanent`) membersihkan seluruh baris terkait pada `ticket_activities`, `ticket_attachments`, `ticket_ratings`, dan `ticket_relationships` di level aplikasi sebelum baris tiket dihapus (tanpa ON DELETE CASCADE / foreign keys).

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
