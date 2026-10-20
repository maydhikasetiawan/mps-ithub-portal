# Arsitektur Sistem MPS-ITHub Portal

Dokumen ini menjelaskan rancangan arsitektur, tumpukan teknologi (*technology stack*), tata letak repositori, modul rute, skema basis data, model otentikasi & hak akses, serta alur *deployment pipeline*.

---

## 1. Tumpukan Teknologi (Tech Stack)

- **Backend Framework**: Python 3.11, Flask 3.0.2, Werkzeug 3.0.1 (dengan middleware `ProxyFix` untuk reverse proxy)
- **Production WSGI Server**: Gunicorn 26.2.0 (server pengembangan Flask bawaan tidak digunakan di lingkungan produksi)
- **Template Engine & UI**: Jinja2 dengan Vanilla Custom CSS (tanpa framework CSS eksternal seperti Bootstrap/Tailwind)
- **Database & Migration**: PostgreSQL, driver `psycopg2-binary` 2.9.9 (`RealDictCursor`), skema migrasi menggunakan Alembic 1.13.1
- **Image Processing & QR**: Pillow 10.2.0, qrcode 8.2 (pembangkitan QR server-side in-memory)
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
├── entrypoint.sh         # Container entrypoint (menjalankan alembic upgrade head, lalu memulai Gunicorn)
└── requirements.txt      # Daftar dependensi Python
```

---

## 3. Rincian Modul Aplikasi (Modules & Key Routes)

Aplikasi dibangun berbasis modul Blueprint Flask:

### a. `auth` (`routes/auth.py`, URL prefix: root)
- **Tujuan**: Menangani autentikasi sesi, pembatasan brute force (*rate limiting* 5 kali gagal per jendela 15 menit per IP/username), dan dekorator izin akses.
- **Rute Utama**:
  - `GET, POST /login` — Halaman dan pemrosesan autentikasi login pengguna.
  - `POST /logout` — Menghapus sesi dan mengarahkan kembali ke halaman login (POST-only; dipicu melalui dropdown profil dengan konfirmasi modal "Keluar dari aplikasi?").

### b. `dashboard` (`routes/dashboard.py`, URL prefix: root)
- **Tujuan**: Menampilkan statistik ringkasan operasional secara waktu nyata, 4 grafik server-rendered SVG (grafik harian "Tiket Baru — 30 Hari Terakhir" / `daily_chart_svg`, tiket per kategori, tiket per status, dan aset per status) yang menggunakan palet Fase 5.3, tabel HTML kondisional "Garansi Akan Habis" (muncul hanya jika terdapat aset mendekati habis garansi), serta baris tren komparasi 30 hari (tiket dibuat/diselesaikan periode 30 hari berjalan vs 30 hari sebelumnya) tanpa dependensi eksternal maupun migrasi basis data.
- **Rute Utama**:
  - `GET /` & `GET /dashboard` — Agregasi total aset aktif, jumlah tiket terbuka/dalam pengerjaan, persentase ketersediaan layanan (*uptime percentage*), 4 grafik analitis SVG 30 hari, tabel HTML garansi kondisional, dan metrik tren.
  - Endpoint JSON untuk topbar: `/api/search` (pencarian global) dan `/api/notifications` (lonceng notifikasi) — keduanya di balik `login_required`.

### c. `assets` (`routes/assets.py`, URL prefix: `/assets`)
- **Tujuan**: Manajemen inventaris aset TI dan IP Address Management (IPAM). Mendukung pencatatan aset, nomor seri perangkat (`serial_number` pada formulir tambah/edit, halaman detail, dan impor), penghitungan usia perangkat, validasi keunikan tag aset, penugasan perangkat, pemantauan masa garansi dan opsi tanpa garansi, jejak audit riwayat perubahan (*asset activities*), impor massal dari CSV, pencetakan label fisik QR, soft delete beralasan, pemulihan (*restore*), serta penghapusan permanen khusus admin dengan verifikasi ganda.
- **Rute Utama**:
  - `GET /assets/` — Daftar aset aktif dengan filter pencarian, status, dan penugasan pengguna.
  - `GET, POST /assets/add` — Formulir penambahan aset baru dengan penugasan, nomor seri, dan masa garansi.
  - `GET /assets/<int:asset_id>` — Detail spesifikasi (termasuk nomor seri), linimasa riwayat perubahan, status garansi dinamis, dan kalkulasi usia aset.
  - `GET, POST /assets/edit/<int:asset_id>` — Pembaruan informasi perangkat (termasuk nomor seri) dengan pencatatan jejak audit otomatis.
  - `GET, POST /assets/import` — Impor massal data aset dari berkas CSV dengan template 13 kolom dengan `serial_number` opsional (CSV lama 12 kolom tetap diterima) dan transaksi atomik (*all-or-nothing*).
  - `GET /assets/import/template` — Unduh template CSV aset siap pakai (`template_import_aset.csv`) yang dibangkitkan secara *in-memory* (header 13 kolom).
  - `GET /assets/<int:asset_id>/label` — Tampilan label QR fisik siap cetak untuk perangkat tertentu (pembangkitan QR *server-side* via qrcode/Pillow).
  - `GET, POST /assets/delete/<int:asset_id>` — Soft delete aset ke riwayat terhapus.
  - `POST /assets/restore/<int:asset_id>` — Mengembalikan aset terhapus ke status aktif.
  - `GET /assets/deleted-history` — Riwayat seluruh aset yang berstatus terhapus.
  - `GET /assets/deleted-detail/<int:asset_id>` — Detail informasi aset terhapus.
  - `GET, POST /assets/hard-delete/<int:asset_id>` — Hapus permanen dari basis data (konfirmasi nama dan kata sandi admin).

### d. `tickets` (`routes/tickets.py`, URL prefix: `/tickets`)
- **Tujuan**: Layanan helpdesk/service desk internal. Pembuatan kode tiket otomatis (`TCK-YYYYMMDD-XXX`), filter status, penyelesaian masalah (*resolution note*), penugasan staf, penambahan komentar, kalkulasi Service Level Agreement (SLA) otomatis, serta pencatatan linimasa aktivitas terpadu dan manajemen kategori dinamis. Seluruh fitur tiket Fase 2 (penilaian kepuasan CSAT, buka ulang tiket/reopen, template respon/canned responses, dan relasi tiket/relationships) beroperasi di dalam blueprint ini melalui aksi dispatch pada `detail()` serta rute `/tickets/canned-responses*`.
- **Rute Utama**:
  - `GET /tickets/` — Daftar tiket dengan paginasi (20 per halaman via `COUNT` + `LIMIT`/`OFFSET`). Pengguna reguler (`user` dan `guest`) hanya melihat tiket miliknya sendiri; mendukung filter status dan parameter `assignee`: `all`, `unassigned`, `me`; dilengkapi badge SLA).
  - `GET /tickets/api/new-count` — Endpoint polling berkala untuk menghitung jumlah tiket baru sejak baseline `since_id` pengguna (Admin/IT, mengembalikan JSON `{"new_count": N, "latest_id": M}`).
  - `GET, POST /tickets/add` — Pembuatan laporan masalah baru beserta pencatatan otomatis aktivitas `created`.
  - `GET, POST /tickets/<int:ticket_id>` — Detail tiket beserta blok target/status SLA dan linimasa aktivitas (mencakup pencatatan `created`, `status`, `assignment`, `comment`, unggah lampiran `attachment`, penilaian CSAT `rating`, dan pembaruan catatan resolusi saja `note`); penanganan POST terbagi: penambahan komentar (`action=comment`, admin/it/user pada tiketnya), pembaruan status/assignee (`action=update_status`, admin/it), penilaian CSAT (`action=submit_rating`, reporter tiket), buka ulang tiket (`action=reopen`, reporter/admin/it), penautan relasi tiket (`action=link`, admin/it), dan pemutusan relasi (`action=unlink`, admin/it).
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
  - **Mekanisme Pengiriman**: Pengiriman asinkron non-blocking (`enqueue_webhook`) yang melakukan `INSERT` ke tabel `webhook_deliveries` menggunakan koneksi basis data mandiri dan langsung di-commit. Setiap pengiriman diproses oleh satu background daemon thread terpisah dengan mekanisme coba ulang (*retry*) hingga 3 kali percobaan (jeda *backoff* 2 detik dan 4 detik). Pengiriman dianggap sukses bila respons HTTP 2xx, dan berstatus `failed` setelah kegagalan pada percobaan ke-3. Struktur payload byte-identical dengan desain awal, dan kegagalan pengiriman webhook tidak akan pernah menggagalkan operasi tiket.
  - **Log Pengiriman**: Seluruh riwayat pengiriman dicatat dalam tabel `webhook_deliveries` dengan kolom `event`, `ticket_id`, `ticket_code`, `payload` (JSONB), `webhook_url`, `status` (`pending`/`delivered`/`failed`), `attempts`, `last_error`, `response_status`, `created_at`, dan `delivered_at`.
- **Lampiran Berkas (File Attachments)**:
  - **Penyimpanan Berkas**: Disimpan di sistem berkas (*filesystem*) pada folder `uploads/` (dapat dikonfigurasi melalui variabel lingkungan `UPLOAD_FOLDER`, *default*: `uploads`). *Catatan Volume*: Perubahan kode ini tidak mempertahankan berkas saat container dibuat ulang; persistensi memerlukan volume mount permanen pada konfigurasi deployment server.
  - **Batas Unggahan**: Maksimal 2 berkas per tiket (total eksisting + baru), maksimal 5 MB per berkas. Ekstensi yang diizinkan (*allowlist*): `png`, `jpg`, `jpeg`, `gif`, `webp`, `pdf`, `txt`, `log`, `doc`, `docx`, `xls`, `xlsx`, `csv`. Ekstensi di luar daftar ditolak otomatis dengan pesan error.
  - **Aturan Kompresi**: Berkas gambar (`png`, `jpg`, `jpeg`, `webp`) otomatis diperkecil menggunakan Pillow (dimensi sisi terpanjang maksimal 1920px, hanya *downscale* tanpa memperbesar), dikonversi RGBA/palette ke RGB, dan disimpan dalam format JPEG kualitas 70 dengan ekstensi `.jpg`. Berkas `gif` dan non-gambar disimpan apa adanya (*as-is*).
  - **Keamanan Nama Berkas**: Nama berkas di filesystem menggunakan `uuid4().hex` acak untuk mencegah *path traversal*. Nama asli diamankan via `secure_filename` dan disimpan di basis data untuk tampilan/unduhan. Akses unduh divalidasi via rute `send_file` (bukan static path).

### e. `uptime` (`routes/uptime.py`, URL prefix: `/uptime`)
- **Tujuan**: Pemantauan ketersediaan target server/layanan melalui pengecekan TCP port atau HTTP request beserta pencatatan latensi (ms). Pengecekan otomatis terjadwal dengan interval dari variabel lingkungan `UPTIME_CHECK_INTERVAL` (default: 300 detik; scheduler in-app, daemon thread), alert DOWN/PULIH berbasis transisi (in-app + Telegram), dan riwayat cek per monitor dengan grafik latensi.
- **Rute Utama**:
  - `GET /uptime/` — Dasbor status monitor dan ringkasan target aktif/mati (admin, it, guest).
  - `GET, POST /uptime/add` — Menambahkan target baru dengan uji kesehatan instan (admin, it).
  - `GET /uptime/check/<int:monitor_id>` — Uji ulang kesehatan satu target / Cek Now (admin, it, guest). Manual check does NOT count toward the 2-consecutive-DOWN alert confirmation.
  - `GET /uptime/check-all` — Uji ulang seluruh target sekaligus (admin, it, guest).
  - `GET, POST /uptime/edit/<int:monitor_id>` — Ubah target monitor; re-check instan saat monitor aktif (admin, it).
  - `POST /uptime/toggle/<int:monitor_id>` — Nyalakan/matikan pemantauan otomatis per monitor (admin, it).
  - `POST /uptime/delete/<int:monitor_id>` — Menghapus target monitor beserta alert dan riwayat cek-nya (cascade app-level) (admin, it).
  - `GET /uptime/<int:monitor_id>/history` — Riwayat cek per monitor: grafik latensi SVG + statistik (uptime %, rata-rata/min/maks latensi, total cek, jumlah DOWN), rentang 24 jam / 7 hari / 30 hari (admin, it, guest).
  - `GET, POST /uptime/telegram-settings` — Pengaturan Telegram (bot token + chat ID, disimpan di database, token tidak pernah dirender) — ADMIN ONLY.
  - `POST /uptime/telegram-test` — Kirim pesan tes ke Chat ID tersimpan — ADMIN ONLY.
- **Pengecekan Terjadwal (Scheduler)**: Daemon thread yang dijalankan saat startup aplikasi (`start_uptime_scheduler()`) dengan interval dari variabel lingkungan `UPTIME_CHECK_INTERVAL` (default 300 detik). Hanya memeriksa monitor dengan `enabled = TRUE`, menggunakan fungsi *helper* `run_all_checks()` yang sama dengan rute manual *Check All*.
- **Mekanisme Alert (Transisi Status & Telegram)**: Alert hanya dikirim saat terjadi transisi status (`UP → DOWN` menghasilkan alert DOWN, `DOWN → UP` menghasilkan alert PULIH). Alert DOWN hanya terpicu pada pengecekan DOWN berturut-turut kedua jika belum ada alert aktif (flag `is_alerted` pada `monitors`); alert PULIH terpicu saat status kembali UP jika dan hanya jika terdapat alert yang sedang aktif. Flag `is_alerted` (bukan counter) berfungsi sebagai status alert, sehingga reset counter saat toggle tidak lagi menimbulkan duplikasi alert DOWN atau hilangnya alert PULIH. Baris alert disimpan dan di-*commit* ke basis data terlebih dahulu sebelum pengiriman pesan Telegram dicoba (*fail-safe*, kegagalan Telegram tidak membatalkan riwayat in-app maupun siklus scheduler). Pengiriman Telegram menggunakan pustaka standar Python `urllib` tanpa dependensi eksternal.
- **Riwayat Pengecekan & Grafik**: Setiap pengecekan (scheduler, *Check All*, *Cek Now*, *re-check* saat edit, dan cek awal saat penambahan target) mencatat tepat satu baris riwayat ke tabel `uptime_checks`. Pembersihan otomatis (*retention cleanup*) menghapus data riwayat yang lebih lama dari 30 hari di dalam `run_all_checks()`. Tampilan rentang 24 jam menggunakan titik data mentah, sedangkan rentang 7 hari dan 30 hari menggunakan agregasi per jam (*hourly buckets*) dengan kalkulasi agregat mentah `MIN`/`MAX`/`SUM` untuk menjaga keakuratan nilai statistik latensi (fix f0c0368). Grafik latensi SVG dilengkapi garis kisi atas (*top gridline*) pada y=20 dan rata-rata latensi per *bucket* dibulatkan seragam ke 1 desimal.

### f. `users` (`routes/users.py`, URL prefix: `/users`)
- **Tujuan**: Administrasi pengguna dan struktur departemen organisasi, reset password administratif dengan flag wajib ganti, antarmuka penggantian kata sandi mandiri, soft-delete akun dengan formulir pencatatan alasan, halaman riwayat user terhapus, pemulihan (*restore*), serta penghapusan permanen (*hard delete*) khusus admin dengan verifikasi ganda (ketik username + kata sandi admin). Seluruh kueri operasional memfilter `is_deleted = FALSE` (termasuk autentikasi login), dan konstrain UNIQUE username/email tetap mencegah duplikasi identitas.
- **Rute Utama**:
  - `GET /users/` — Daftar pengguna aktif (`is_deleted = FALSE`).
  - `GET, POST /users/add` — Pendaftaran akun pengguna baru.
  - `GET, POST /users/edit/<int:user_id>` — Pembaruan data pengguna dan opsi reset kata sandi.
  - `GET, POST /users/delete/<int:user_id>` — Soft delete akun pengguna dengan konfirmasi alasan (proteksi akun sendiri).
  - `GET /users/deleted-history` — Riwayat user terhapus dengan fitur pencarian username/email/alasan.
  - `GET /users/deleted-detail/<int:user_id>` — Detail akun user terhapus.
  - `POST /users/restore/<int:user_id>` — Mengembalikan akun user terhapus ke daftar aktif.
  - `GET, POST /users/hard-delete/<int:user_id>` — Penghapusan permanen akun user (verifikasi username + kata sandi admin).
  - `GET, POST /users/departments` — Pengelolaan daftar departemen.
  - `GET /users/departments/delete/<int:dept_id>` — Hapus departemen (proteksi bila masih ada user terkait).
  - `GET, POST /users/change-password` — Penggantian kata sandi mandiri bagi pengguna aktif.
- **Jejak Audit Aktivitas (Audit Trail)**: Setiap mutasi pengguna dan departemen mencatat satu baris riwayat ke tabel `user_activities` (mencakup `actor`, `type`, `content`, di dalam transaksi yang sama). Mendukung 11 tipe peristiwa: `user_created`, `user_soft_deleted`, `user_restored`, `user_hard_deleted`, `department_created`, `department_deleted`, `role_changed`, `password_reset`, `email_changed`, `department_changed`, dan `password_changed`. Tidak ada antarmuka UI untuk log ini (DB-only).

### g. `reports` (`routes/reports.py`, URL prefix: `/reports`)
- **Tujuan**: Penyediaan laporan analitis dan ekspor data tabular ke berkas CSV dengan format UTF-8-SIG untuk kompatibilitas Microsoft Excel. Mengikuti struktur 4 bagian standar Fase 4:
  - **Header Block**: Judul laporan (`Laporan IT Service Desk & Helpdesk` / `Laporan Aset IT`), tanggal dibuat laporan, pembuat laporan (`Dibuat Oleh`), dan filter aktif.
  - **Summary Block**: Total data dan rekapitulasi ringkasan (laporan tiket: total tiket, breakdown status, prioritas, kategori, rata-rata durasi penyelesaian, % SLA terpenuhi, rata-rata CSAT; laporan aset: total aset, breakdown status, breakdown kategori).
  - **Detail Columns**: Baris detail data tabular. Ekspor tiket terdiri dari 17 kolom termasuk `Assignee`, `SLA`, `Durasi Penyelesaian`, `CSAT`, dan `Terakhir Diperbarui`. Ekspor aset terdiri dari 18 kolom termasuk `Serial Number`, `Assigned To`, `Purchase Date`, dan `Warranty Expiry`.
  - **Footer**: Baris penutup yang memuat total baris data (`Total Baris Data: N`).
- **Rute Utama**:
  - `GET /reports/` — Antarmuka pemilihan filter laporan.
  - `GET /reports/export/assets` — Unduh data aset dalam bentuk CSV (18 kolom detail dengan header, summary, dan footer).
  - `GET /reports/export/tickets` — Unduh data tiket helpdesk dalam bentuk CSV (17 kolom detail dengan header, summary, dan footer).

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

### j. `api` (`routes/api.py`, URL prefix: `/api/v1`)
- **Tujuan**: REST API read-only terpusat untuk integrasi eksternal (tiket, aset TI, dan target monitor). Autentikasi kunci tunggal dari variabel lingkungan `API_KEY` via header `X-API-Key` (fail-closed 401). Mendukung paginasi `limit`/`offset` dan otomatis mengecualikan entitas yang berstatus soft-deleted. Endpoint monitor membaca tabel riil `monitors`. Dokumentasi referensi lengkap: [docs/API.md](API.md).
- **Rute Utama**:
  - `GET /api/v1/tickets` & `GET /api/v1/tickets/<int:ticket_id>` — Daftar dan detail tiket bantuan aktif.
  - `GET /api/v1/assets` & `GET /api/v1/assets/<int:asset_id>` — Daftar dan detail aset TI aktif.
  - `GET /api/v1/monitors` & `GET /api/v1/monitors/<int:monitor_id>` — Daftar dan detail status target uptime monitor.

### i. `branding` (`routes/branding.py`, URL prefix: `/settings`)
- Halaman pengaturan branding white-label per instalasi (khusus admin); data dari tabel `branding_settings` dibaca fail-safe oleh `get_branding()` di `database/db.py` dan disuntikkan ke template via context processor.

---

## 4. Skema Basis Data (Database Schema)

Skema dibentuk sepenuhnya melalui migrasi Alembic (`001–023`, dengan tabel dasar didefinisikan pada migrasi `001` dan data bawaan kategori pada `020`, serta 009 sebagai pembersihan data yatim satu kali tanpa perubahan skema):

1. **`users`**
   - Kolom: `id` (PK, Serial), `username` (VARCHAR 50, Unique), `email` (VARCHAR 100, Unique), `password_hash` (TEXT), `role` (VARCHAR 20, default 'staff'), `department` (VARCHAR 50, default 'IT'), `must_change_password` (BOOLEAN, default FALSE), `is_deleted` (BOOLEAN, default FALSE, Migrasi 019), `deleted_at` (TIMESTAMP, Migrasi 019), `deleted_by` (VARCHAR 50, Migrasi 019), `delete_reason` (TEXT, Migrasi 019), `created_at` (TIMESTAMP). Indeks: `idx_users_is_deleted`.
2. **`assets`**
   - Kolom: `id` (PK, Serial), `asset_tag` (VARCHAR 50, Unique), `serial_number` (VARCHAR 100, Migrasi 014), `name` (VARCHAR 100), `category` (VARCHAR 50), `ip_address` (VARCHAR 45), `mac_address` (VARCHAR 45), `status` (VARCHAR 20, default 'Active'), `location` (VARCHAR 100), `notes` (TEXT), `assigned_to` (VARCHAR 50, Migrasi 010), `purchase_date` (DATE, Migrasi 011), `warranty_expiry` (DATE, Migrasi 011), `no_warranty` (BOOLEAN, default FALSE, Migrasi 012), `is_deleted` (BOOLEAN, default FALSE), `deleted_at` (TIMESTAMP), `deleted_by` (VARCHAR 50), `delete_reason` (TEXT), `created_at` (TIMESTAMP), `updated_at` (TIMESTAMP), `updated_by` (VARCHAR 50).
3. **`tickets`**
   - Kolom: `id` (PK, Serial), `ticket_code` (VARCHAR 20, Unique), `title` (VARCHAR 150), `category` (VARCHAR 50), `priority` (VARCHAR 20, default 'Medium'), `status` (VARCHAR 20, default 'Open'), `description` (TEXT), `created_by` (VARCHAR 50), `assigned_to` (VARCHAR 50), `department` (VARCHAR 50), `resolution_note` (TEXT), `resolved_by` (VARCHAR 50), `resolved_at` (TIMESTAMP), `is_deleted` (BOOLEAN, default FALSE), `deleted_at` (TIMESTAMP), `deleted_by` (VARCHAR 50), `delete_reason` (TEXT), `created_at` (TIMESTAMP).
4. **`ticket_categories`**
   - Kolom: `id` (PK, Serial), `name` (VARCHAR 50, Unique).
   - Data bawaan: 'Hardware', 'Network', 'Software', 'Server', 'Request'.
5. **`departments`**
   - Kolom: `id` (PK, Serial), `name` (VARCHAR 50, Unique).
6. **`monitors`**
   - Kolom: `id` (PK, Serial), `name` (VARCHAR 100), `target` (VARCHAR 255), `type` (VARCHAR 20, default 'PING'), `port` (INT), `status` (VARCHAR 20, default 'UNKNOWN'), `latency` (INT, default 0), `last_check` (TIMESTAMP), `enabled` (BOOLEAN, default TRUE, migrasi 015), `consecutive_failures` (INT, default 0, migrasi 016), `is_alerted` (BOOLEAN, default FALSE, migrasi 022), `created_at` (TIMESTAMP).
7. **`ticket_activities`**
   - Kolom: `id` (PK, Serial), `ticket_id` (INT, Not Null), `actor` (VARCHAR 50), `type` (VARCHAR 20), `content` (TEXT), `created_at` (TIMESTAMP).
   - Menyimpan seluruh linimasa peristiwa tiket: `'created'`, `'status'`, `'assignment'`, `'comment'`, `'attachment'`, `'rating'`, dan `'note'`.
8. **`ticket_attachments`**
   - Kolom: `id` (PK, Serial), `ticket_id` (INT, Not Null), `stored_filename` (VARCHAR 255, Not Null), `original_filename` (VARCHAR 255, Not Null), `size_bytes` (INT, Not Null), `mime_type` (VARCHAR 100), `uploader` (VARCHAR 50), `created_at` (TIMESTAMP).
   - Menyimpan seluruh metadata berkas lampiran tiket.
9. **`kb_articles`** *(Migrasi 005)*
    - Kolom: `id` (PK, Serial), `title` (VARCHAR 255, Not Null), `category` (VARCHAR 100, Not Null), `content` (TEXT, Not Null), `tags` (VARCHAR 255), `status` (VARCHAR 20, default 'draft', check draft/published), `author` (VARCHAR 50), `created_at` (TIMESTAMP), `updated_at` (TIMESTAMP).
    - Tujuan: Menyimpan artikel panduan teknis dan solusi masalah Knowledge Base.
10. **`ticket_ratings`** *(Migrasi 006)*
    - Kolom: `id` (PK, Serial), `ticket_id` (INT, Not Null, Unique), `rating` (INT, Not Null, check 1-5), `comment` (TEXT), `rater` (VARCHAR 50), `created_at` (TIMESTAMP), `updated_at` (TIMESTAMP).
    - Tujuan: Menyimpan penilaian kepuasan layanan (CSAT) dari pelapor tiket.
11. **`canned_responses`** *(Migrasi 007)*
    - Kolom: `id` (PK, Serial), `title` (VARCHAR 255, Not Null), `content` (TEXT, Not Null), `category` (VARCHAR 100, default 'Umum'), `author` (VARCHAR 50), `created_at` (TIMESTAMP), `updated_at` (TIMESTAMP).
    - Tujuan: Menyimpan pustaka template balasan komentar Service Desk bagi Admin dan IT.
12. **`ticket_relationships`** *(Migrasi 008)*
    - Kolom: `id` (PK, Serial), `ticket_a_id` (INT, Not Null), `ticket_b_id` (INT, Not Null), `relation_type` (VARCHAR 20, Not Null: 'duplicate' / 'related'), `created_by` (VARCHAR 50), `created_at` (TIMESTAMP).
    - Tujuan: Menyimpan hubungan keterkaitan antar-tiket. Konvensi penyimpanan: `ticket_a_id` = tiket duplikat (sumber), `ticket_b_id` = tiket kanonikal (target). Keunikan pasangan kedua arah ditegakkan di level aplikasi tanpa constraint UNIQUE DB.
13. **`asset_activities`** *(Migrasi 013)*
    - Kolom: `id` (PK, Serial), `asset_id` (INT, Not Null), `actor` (VARCHAR 50), `action` (VARCHAR 20, Not Null), `field_name` (VARCHAR 50), `old_value` (TEXT), `new_value` (TEXT), `created_at` (TIMESTAMP).
    - Tujuan: Menyimpan linimasa jejak audit (*audit trail*) riwayat perubahan data aset untuk aksi `created`, `updated`, `soft-deleted`, dan `restored`.
14. **`uptime_alerts`** *(Migrasi 016)*
    - Kolom: `id` (PK, Serial), `monitor_id` (INT, Not Null, NO foreign key — codebase convention), `alert_type` (VARCHAR 20: 'DOWN' / 'RECOVERED'), `message` (TEXT), `created_at` (TIMESTAMP). Deleted app-level with the monitor.
15. **`telegram_settings`** *(Migrasi 017)*
    - Kolom: singleton row (`id` = 1), `bot_token` (TEXT), `chat_id` (VARCHAR 64), `updated_at` (TIMESTAMP). Seeded by the migration.
16. **`uptime_checks`** *(Migrasi 018)*
    - Kolom: `id` (PK, Serial), `monitor_id` (INT, Not Null, NO foreign key), `checked_at` (TIMESTAMP), `status` (VARCHAR 10: 'UP' / 'DOWN'), `latency` (INT, ms). Index `idx_uptime_checks_monitor_time` on (`monitor_id`, `checked_at`). Deleted app-level with the monitor.
17. **`webhook_deliveries`** *(Migrasi 021)*
    - Kolom: `id` (PK, Serial), `event` (VARCHAR 50, Not Null), `ticket_id` (INT), `ticket_code` (VARCHAR 20), `payload` (JSONB, Not Null), `webhook_url` (TEXT, Not Null), `status` (VARCHAR 20, default 'pending'), `attempts` (INT, default 0), `last_error` (TEXT), `response_status` (INT), `created_at` (TIMESTAMP), `delivered_at` (TIMESTAMP). Indeks: `idx_webhook_deliveries_status`, `idx_webhook_deliveries_created_at`.
18. **`user_activities`** *(Migrasi 023)*
    - Kolom: `id` (PK, Serial), `user_id` (INT, nullable, tanpa foreign key), `actor` (VARCHAR 50), `type` (VARCHAR 30, Not Null), `content` (TEXT, Not Null), `created_at` (TIMESTAMP). Indeks: `idx_user_activities_user`.
    - Kolom: `id` (PK, Serial), `monitor_id` (INT, Not Null, NO foreign key), `checked_at` (TIMESTAMP), `status` (VARCHAR 10: 'UP' / 'DOWN'), `latency` (INT, ms). Index `idx_uptime_checks_monitor_time` on (`monitor_id`, `checked_at`). Deleted app-level with the monitor.

*Relasi Relasional*:
Hubungan antar-tabel dijaga secara logis di tingkat aplikasi:
- `tickets.created_by`, `tickets.assigned_to`, `tickets.resolved_by`, `assets.assigned_to`, `assets.updated_by`, `assets.deleted_by` berelasi logis ke `users.username`.
- `ticket_activities.ticket_id`, `ticket_attachments.ticket_id`, dan `ticket_ratings.ticket_id` berelasi logis ke `tickets.id`.
- `ticket_relationships.ticket_a_id` dan `ticket_relationships.ticket_b_id` berelasi logis ke `tickets.id`.
- `asset_activities.asset_id` berelasi logis ke `assets.id`.
- `ticket_activities.actor`, `ticket_attachments.uploader`, `ticket_ratings.rater`, `canned_responses.author`, `kb_articles.author`, `ticket_relationships.created_by`, dan `asset_activities.actor` berelasi logis ke `users.username`.
- `users.department` dan `tickets.department` berelasi logis ke `departments.name`.
- `tickets.category`, `kb_articles.category`, dan `canned_responses.category` berelasi logis ke `ticket_categories.name`.
- `webhook_deliveries.ticket_id` berelasi logis ke `tickets.id`.
- `user_activities.user_id` (nullable, tanpa foreign key agar jejak audit tetap bertahan setelah hard deletion) dan `user_activities.actor` berelasi logis ke `users.id` dan `users.username`.
- Penghapusan permanen tiket (`delete_permanent`) membersihkan seluruh baris terkait pada `ticket_activities`, `ticket_attachments`, `ticket_ratings`, dan `ticket_relationships` di level aplikasi sebelum baris tiket dihapus (tanpa ON DELETE CASCADE / foreign keys).
- Penghapusan permanen aset (`hard_delete`) membersihkan seluruh baris linimasa terkait pada `asset_activities` sebelum baris aset dihapus.
- Penghapusan target monitor membersihkan seluruh baris terkait pada `uptime_alerts` dan `uptime_checks` di level aplikasi sebelum baris monitor dihapus.

---

## 5. Autentikasi dan Manajemen Peran (Auth & Roles)

Sistem menggunakan session cookies terenkripsi (`SECRET_KEY`) dengan proteksi dua lapis:
1. `@login_required`: Memastikan pengunjung telah memiliki sesi aktif (`session['user_id']`).
2. `@roles_required(*allowed_roles)`: Memverifikasi nilai `session['role']` sesuai daftar peran yang diizinkan.

### Kedaluwarsa Sesi (Idle Session Timeout):
- Dikonfigurasi dengan batas waktu tidak aktif 30 menit melalui `PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)`.
- Pengaturan `SESSION_REFRESH_EACH_REQUEST = True` memastikan cookie kedaluwarsa diperbarui setiap ada permintaan baru (*rolling idle timeout*).
- Status permanen sesi diaktifkan khusus saat login berhasil (`session.permanent = True` di `routes/auth.py`). Sesi anonim tidak pernah dijadikan permanen.
- Jika pengguna idle melampaui 30 menit, permintaan atau klik berikutnya mendapati sesi telah kedaluwarsa dan `@login_required` maupun `@roles_required` otomatis mengarahkan ke `/login` disertai notifikasi flash satu kali: `Sesi Anda telah berakhir. Silakan login kembali.`. Mekanisme ini menggunakan marker cookie `mps_had_session` yang disetel saat login dan dihapus pada respon pengalihan kedaluwarsa (pesan tidak pernah muncul bagi pengunjung baru pertama kali maupun setelah aksi logout yang disengaja).

### Middleware ProxyFix (Reverse Proxy Trust):
- Aplikasi dibungkus oleh middleware Werkzeug `ProxyFix` pada `app.py`:
  ```python
  app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
  ```
- Mengonfigurasi aplikasi agar mempercayai header `X-Forwarded-For`, `X-Forwarded-Proto`, dan `X-Forwarded-Host` dari tepat 1 *hop* reverse proxy Nginx. Hal ini memastikan pembentukan URL absolut seperti `url_for(..., _external=True)` (digunakan untuk muatan kode QR label aset) menghasilkan skema protokol `https://` yang sesuai dengan akses peramban pengguna.
- **Catatan Prasyarat**: `ProxyFix` hanya berdampak jika reverse proxy Nginx meneruskan skema protokol asli klien melalui header `X-Forwarded-Proto` (konfigurasi tingkat server di luar repositori).

### Peran Pengguna:
- **`admin`**: Memiliki hak akses penuh mencakup manajemen pengguna, departemen, penghapusan permanen tiket dan aset, manajemen kategori, dan seluruh modul operasional.
- **`it`**: Tim teknis IT yang dapat mengelola aset (tambah/edit/soft delete/restore), memperbarui status tiket dan catatan solusi, serta mengelola target uptime monitor.
- **`user`**: Pengguna reguler internal yang hanya dapat melihat dan membuat tiket miliknya sendiri, serta melakukan penggantian kata sandi mandiri.
- **`guest`**: Akses baca (*read-only*) untuk meninjau dasbor, daftar aset, riwayat aset terhapus, tiket, dan uptime monitor tanpa izin modifikasi data.

Sistem juga menerapkan middleware `check_mandatory_password_change` pada `app.py` yang memaksa redirect ke `/users/change-password` jika nilai flag `session['must_change_password']` bernilai `True`.

---

## 6. Alur Pipeline Penerapan (Deploy Pipeline)

Otomatisasi pengiriman kode ke server produksi diatur melalui GitHub Actions pada file `.github/workflows/deploy.yml`:

- **Concurrency Guard**: Dikonfigurasi dengan `concurrency: group: deploy-production, cancel-in-progress: false`. Jika terjadi merge/push beruntun ke `main`, proses deploy kedua akan mengantre dan deploy yang sedang berjalan tidak pernah dibatalkan di tengah jalan (*never killed mid-way*) guna menghindari kondisi inkonsistensi kontainer produksi.
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
     - Menjalankan container baru di port `5000:5000` dengan kebijakan restart otomatis (`--restart always`) serta menginjeksikan secrets: `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASS`, `SECRET_KEY`, dan `API_KEY` (via `-e API_KEY=${{ secrets.API_KEY }}`). Container memulai proses via `entrypoint.sh` yang menjalankan migrasi otomatis `alembic upgrade head` (bersifat idempoten — no-op bila sudah di head) sebelum menjalankan server produksi Gunicorn 26.2.0 dengan perintah: `gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 --timeout 45 --graceful-timeout 30 --forwarded-allow-ips="*" --access-logfile - --error-logfile - --log-level info app:app` (model worker `gthread`, PID 1, log akses dan error ke stdout). Prosedur rollback dilakukan dengan melakukan revert commit pada Git (`git revert`).

## 7. Sistem Tema & Antarmuka (UI Theme System)

- **Satu berkas gaya terpusat**: Seluruh tampilan aplikasi diatur oleh `static/css/theme.css` (Fase 7.1). Tidak ada blok `<style>` per halaman dan tidak ada atribut `style=""` inline di templat, kecuali pengecualian yang disengaja di bawah.
- **Token desain**: Nilai warna, radius, dan bayangan didefinisikan sebagai variabel CSS pada `:root` (tema gelap, bawaan) dan diganti pada `[data-theme="light"]` (tema terang). Komponen hanya memakai variabel token (mis. `var(--surface)`, `var(--text)`, `var(--accent)`), tidak ada warna hex langsung di aturan komponen.
- **Dua tema aktif**: Gelap (bawaan) dan terang, diganti lewat tombol toggle di header. Pilihan disimpan di `localStorage` dengan kunci `mpshub-theme`; skrip kecil di `<head>` menerapkan tema sebelum render agar tidak ada kedipan tema yang salah. Halaman login juga mendukung kedua tema.
- **Tipografi**: Public Sans untuk teks dan IBM Plex Mono untuk kode/nilai mono, dimuat dari Google Fonts dengan fallback fon sistem.
- **Ikon**: Tetap memakai emoji; tidak ada set ikon SVG.
- **Responsif**: Di bawah 620px, tabel `.data-table` berubah menjadi pola kartu memakai atribut `data-label` pada setiap sel data sebagai nama kolom. Target sentuh kontrol interaktif minimal 44px.
- **Lapisan gerak (Fase 7.3)**: Animasi masuk halaman dan kartu, animasi modal konfirmasi dan dropdown profil, serta transisi hover/focus — semuanya hanya memakai properti `opacity` dan `transform` (150–300ms) dan dinonaktifkan lewat `@media (prefers-reduced-motion: reduce)`.
- **Pengecualian**: `templates/assets/label.html` (label fisik untuk dicetak) tidak memakai `theme.css` dan tidak bertema — halamannya selalu terang untuk kebutuhan cetak.
- **Hook JavaScript yang tidak boleh diganti namanya**: `#new-ticket-banner` / `.is-visible`, `#confirm-modal`, `#profile-button` / `#profile-dropdown-menu`, `#hamburger-btn` / `.sidebar.open` / `.sidebar-backdrop.open`.
