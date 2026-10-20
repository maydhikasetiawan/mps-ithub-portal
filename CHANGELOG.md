# Changelog

Semua perubahan penting pada proyek **MPS-ITHub Portal** didokumentasikan dalam berkas ini. Format penulisan mengacu pada prinsip Keep a Changelog.

---

## [Unreleased]

## [2026-10-20] - Fase 7: Modernisasi UI
- 7.1 Sentralisasi Gaya (main `eabd55b`): Seluruh gaya inline dan blok `<style>` per halaman dipindah ke satu berkas terpusat `static/css/theme.css`; tidak ada perubahan visual selain perbaikan tombol Telegram Settings.
- 7.2 Penyegaran Tema (5 sub-batch, main `fe70d7a`, `5a04d55`, `163b69f`, `57d6b53`, `12fdb32`, `e149f0a`): Sistem token desain baru dengan dua tema aktif (gelap bawaan + terang, toggle di header, tersimpan di `localStorage` kunci `mpshub-theme`); fon Public Sans + IBM Plex Mono; kolom STATUS dan SLA pada daftar tiket dipisah menjadi dua kolom; tabel menjadi pola kartu berlabel `data-label` pada layar ≤620px.
- 7.3 Lapisan Gerak (main `5fe8673`, fix dropdown `0bfea0f`): Animasi masuk halaman dan kartu (berjenjang), animasi modal konfirmasi (fade + scale) dan dropdown profil, banner tiket baru fade-in, transisi hover/focus tombol, baris tabel, dan input — hanya properti `opacity`/`transform`, 150–300ms, dinonaktifkan oleh `prefers-reduced-motion`.
- 7.4 Perbaikan Mobile & Dokumentasi: Atribut `data-label` untuk tabel garansi dasbor; target sentuh `.page-link`, `.range-btn`, dan `.nav-link` menjadi minimal 44px; dokumentasi sistem tema ditambahkan ke `docs/architecture.md` dan `docs/features.md`.

## [2026-10-18] - Pre-UI Refinements
- Batch 1 Pengamanan Tiket Guest & Log Aktivitas (main `f475c3d`):
  - Memperbaiki celah IDOR tiket guest dengan menambahkan peran `'guest'` pada pemeriksaan kepemilikan tiket (`user_role in ('user', 'guest')`) di rute daftar tiket, detail tiket, dan unduh lampiran berkas.
  - Menambahkan pencatatan entri linimasa `ticket_activities` untuk unggah lampiran berkas (`attachment`), pengiriman rating kepuasan CSAT (`rating`), dan pembaruan catatan penyelesaian tiket saja (`note`).
  - Verifikasi: `python3 -m py_compile` dan `git grep`.
- Batch 1b Otoritas Penuh Skema Alembic (main `18793be`, migrasi 020):
  - Menjadikan Alembic sebagai otoritas tunggal skema basis data dengan memindahkan DDL tabel dasar ke migrasi `001_add_missing_schema_objects.py` (`CREATE TABLE IF NOT EXISTS`) dan menambahkan migrasi `020_default_categories.py` untuk seed kategori tiket awal.
  - Menghapus fungsi `init_db()` beserta pembuatan akun bawaan hardcoded (`admin` dan `guest`) dari `database/db.py` dan `app.py`; akun admin pertama dibuat langsung via psql.
  - Verifikasi: `python3 -m py_compile`, `python3 -m alembic heads` (head 020), dan `git grep`.
- Batch 2 Webhook Asinkron & Log Pengiriman (main `5e71114`, migrasi 021):
  - Migrasi `021_webhook_deliveries.py` membuat tabel `webhook_deliveries` untuk mencatat riwayat pengiriman webhook.
  - Mengganti pengiriman sinkron dengan pengiriman asinkron non-blocking (`enqueue_webhook`) menggunakan thread daemon mandiri dengan mekanisme coba ulang (*retry*) hingga 3 kali (backoff 2s, 4s); kegagalan webhook tidak menggagalkan operasi tiket.
  - Membersihkan dokumentasi akun bawaan lama pada `docs/setup.md`.
  - Verifikasi: `python3 -m py_compile`, `python3 -m alembic heads` (head 021), dan `git grep`.
- Batch 3 Deduplikasi Alert Uptime & Interval Konfigurasi (main `df279a7`, migrasi 022):
  - Migrasi `022_add_monitor_is_alerted.py` menambahkan kolom boolean `is_alerted` pada tabel `monitors`.
  - Pelacakan status alert menggunakan flag `is_alerted`: alert DOWN hanya dikirim pada kegagalan kedua berturut-turut jika belum ada alert aktif; alert PULIH hanya dikirim jika ada alert yang sedang aktif; aksi toggle dan manual check tidak mengubah flag.
  - Interval scheduler uptime dapat dikonfigurasi melalui variabel lingkungan `UPTIME_CHECK_INTERVAL` (default: 300 detik).
  - Grafik latensi SVG menambahkan garis kisi atas (*top gridline*) pada y=20 dan rata-rata latensi per *bucket* dibulatkan seragam ke 1 desimal.
  - Verifikasi: `python3 -m py_compile`, `python3 -m alembic heads` (head 022), dan `git grep`.
- Batch 4 Paginasi Daftar Tiket & Aset (main `6a335de`):
  - Menambahkan paginasi 20 item per halaman (`PER_PAGE = 20`) pada daftar tiket dan daftar aset menggunakan query `COUNT` dan `LIMIT`/`OFFSET` dengan pembatasan halaman (*page clamp*).
  - Menurunkan `latest_ticket_id` dari nilai agregat `MAX(id)` kueri hitung agar polling tiket baru berfungsi akurat di seluruh halaman paginasi.
  - Menghapus variabel tidak terpakai `old_status` pada `routes/uptime.py`.
  - Verifikasi: `python3 -m py_compile` dan `git grep`.
- Batch 5 Jejak Audit User & Departemen (main `074cbc1`, migrasi 023):
  - Migrasi `023_user_activities.py` membuat tabel `user_activities` (`user_id` nullable tanpa foreign key, `actor`, `type` VARCHAR(30), `content`, `created_at`).
  - Menambahkan helper `log_user_activity` pada `routes/users.py` untuk mencatat seluruh 11 mutasi user dan departemen secara atomik dalam satu transaksi (`user_created`, `user_soft_deleted`, `user_restored`, `user_hard_deleted`, `department_created`, `department_deleted`, `role_changed`, `password_reset`, `email_changed`, `department_changed`, `password_changed`). Log tersimpan di basis data tanpa antarmuka UI.
  - Verifikasi: `python3 -m py_compile`, `python3 -m alembic heads` (head 023), dan `git grep`.

## [2026-10-18] - Fase 6: Dashboard, Integrasi & REST API
- Fase 6.1 Grafik & Tren Dasbor (main `69b6c71`, `bd49bdc`):
  - 4 grafik SVG server-rendered tanpa dependensi/CDN (grafik harian "Tiket Baru — 30 Hari Terakhir" / `daily_chart_svg`, tiket per kategori, tiket per status, aset per status) yang menggunakan kembali palet grafik Fase 5.3, serta tabel kondisional "Garansi Akan Habis" (tabel HTML ketika ada aset bergaransi mendekati batas).
  - Baris tren komparasi 30 hari (tiket dibuat dan diselesaikan: 30 hari berjalan vs 30 hari sebelumnya) tanpa migrasi basis data.
- Fase 6.2 Baris Penyelesaian Tiket (main `8a96b45`):
  - Baris "Diselesaikan oleh" hanya dirender jika `resolved_at` terisi; resolver memiliki fallback `-` bila `resolved_by` kosong.
- Fase 6.3 Tanggal Pembuatan & Pembaruan Tiket (main `f0e1b5d`):
  - Halaman detail tiket menampilkan meta tanggal "Dibuat: <created_at> | Terakhir diperbarui: <last_updated>" di mana `last_updated` diambil dari aktivitas tiket terbaru dengan fallback `created_at`.
- Fase 6.4 Soft-Delete User & Riwayat Terhapus (main `3660c7a`, migrasi 019):
  - Migrasi `019_user_soft_delete.py` menambahkan kolom `is_deleted`, `deleted_at`, `deleted_by`, `delete_reason`, dan indeks `idx_users_is_deleted`.
  - Penghapusan user beralih ke soft delete dengan form alasan penghapusan; seluruh query user memfilter `is_deleted = FALSE`, termasuk autentikasi login (user terhapus dilarang login).
  - Halaman riwayat user terhapus (`/users/deleted-history`) dengan pencarian, detail user terhapus (`/users/deleted-detail/<id>`), pemulihan (`restore`), dan hapus permanen (`hard-delete`) dengan konfirmasi ganda (ketik username + kata sandi admin).
  - Batasan UNIQUE username dan email tetap berlaku sehingga mencegah penggunaan ulang nama user yang berstatus soft-deleted; tanpa tabel audit baru.
- Fase 6.5 REST API v1 & Dokumentasi (main `9b1fa15`, `761102a`, `d38ac0a`):
  - Endpoint REST API read-only berprefix `/api/v1` untuk tiket, aset, dan uptime monitor (`GET /api/v1/tickets`, `/api/v1/tickets/<id>`, `/api/v1/assets`, `/api/v1/assets/<id>`, `/api/v1/monitors`, `/api/v1/monitors/<id>`).
  - Autentikasi kunci tunggal dari variabel lingkungan `API_KEY` via header `X-API-Key` dengan verifikasi *constant-time* (`hmac.compare_digest`) dan fail-closed 401; pengecualian data soft-deleted; paginasi standar (`limit` default 20 max 100, `offset` default 0); dokumentasi lengkap di `docs/API.md`.
  - Perbaikan endpoint monitor agar membaca tabel riil `monitors` (migrasi 001/015/016), bukan `service_monitors` warisan `init_db`.
  - Workflow deployment meneruskan rahasia `-e API_KEY=${{ secrets.API_KEY }}` ke container aplikasi.

## [2026-10-16]
- Migrasi Gunicorn (main `16fdf15`):
  - Migrasi server produksi dari server pengembangan Flask bawaan ke Gunicorn 26.2.0 (`1` worker `gthread`, `4` threads, timeout `45`, graceful-timeout `30`, `--forwarded-allow-ips="*"`, log akses dan error ke stdout, PID 1).
  - Perintah eksekusi dipusatkan pada `entrypoint.sh` yang menjalankan migrasi Alembic sebelum menjalankan Gunicorn.
  - Middleware `ProxyFix` tetap berfungsi normal (terverifikasi secara empiris: Gunicorn tidak menghapus `X-Forwarded-Proto`).
  - Prosedur rollback dilakukan dengan melakukan revert commit pada Git (`git revert`).
- Fase 4.1 Laporan Tiket (main `90e4ba6`):
  - Penyempurnaan ekspor laporan tiket CSV (`routes/reports.py`): penambahan header block (judul, tanggal dibuat laporan, pembuat laporan, filter), summary block (total tiket, rincian status, prioritas, kategori, rata-rata durasi penyelesaian, % SLA terpenuhi, rata-rata CSAT), dan footer total baris data (`Total Baris Data`).
  - Penambahan 5 kolom detail baru pada CSV tiket: `Assignee`, `SLA`, `Durasi Penyelesaian`, `CSAT`, dan `Terakhir Diperbarui` (total 17 kolom).
  - Anggaran kueri efisien tepat 3 kueri tanpa masalah N+1 (*no N+1*).
  - Terverifikasi live: 6 tiket, 16.7% SLA, CSAT 5.0/5.
- Serial Number prerequisite (main `a703ab6`, migrasi 014):
  - Penambahan kolom nullable `serial_number VARCHAR(100)` pada tabel `assets` melalui migrasi Alembic `014_add_asset_serial_number.py` dan `init_db()`.
  - Dukungan field nomor seri pada formulir tambah aset, ubah aset, halaman detail spesifikasi, dan pelacakan jejak audit aktivitas (`asset_activities`).
  - Pembaruan template impor CSV menjadi 13 kolom dengan `serial_number` bersifat opsional; berkas CSV lama 12 kolom tetap diterima.
- Fase 4.2+4.3 Laporan Aset (gabung) (main `16f1b26`):
  - Penyempurnaan ekspor laporan aset CSV (`routes/reports.py`): penambahan header block (judul, tanggal dibuat laporan, pembuat laporan, filter), summary block (total aset, rincian status dan kategori), dan footer total baris data (`Total Baris Data`).
  - Penambahan 4 kolom detail baru pada CSV aset: `Serial Number`, `Assigned To`, `Purchase Date`, dan `Warranty Expiry` (total 18 kolom).
  - Tanpa kueri tambahan (tetap 1 kueri tunggal `SELECT *`).
  - Terverifikasi live: 10 aset, seluruh perhitungan konsisten.
- Notifikasi sesi habis (main `eb161c5`):
  - Penerapan marker cookie `mps_had_session` saat login berhasil dan penghapusan saat logout.
  - Penampilan notifikasi flash satu kali `Sesi Anda telah berakhir. Silakan login kembali.` saat pengalihan sesi kedaluwarsa via dekorator `login_required` dan `roles_required`.
  - Blok pesan flash ditambahkan pada `templates/login.html` menggunakan gaya `.alert`.
  - Terverifikasi: 4 kasus perilaku (idle > 30 menit, pengunjung baru, logout, salah password) lulus pengujian.

## [2026-10-16] - Fase 5: Uptime Monitor
- Fase 5.1 Pengecekan otomatis terjadwal (main `0bb1c00`, migrasi 015):
  - Scheduler in-app (daemon thread, interval 300 detik hardcoded — keputusan product owner, tanpa env var / halaman pengaturan).
  - Toggle pemantauan otomatis per monitor (kolom `enabled BOOLEAN DEFAULT TRUE`); monitor nonaktif tampil NONAKTIF + baris redup.
  - Halaman edit monitor (form prefilled, Batal tanpa simpan).
  - Terverifikasi live: toggle OFF/ON round-trip, 5 monitor tetap ON, end state identik.
- Fase 5.2 Alert DOWN/PULIH (main `17e935b`, migrasi 016+017):
  - Alert hanya pada transisi status; DOWN setelah tepat 2 cek DOWN otomatis berurutan (≈10 menit); tetap DOWN tidak re-alert; PULIH sekali setelah episode DOWN yang sudah di-alert kembali UP; Cek Now manual tidak dihitung menuju konfirmasi 2x.
  - Riwayat Alert di halaman Uptime (20 terbaru dari tabel `uptime_alerts`) + banner DOWN + tombol Pengaturan Telegram (admin).
  - Telegram: konfigurasi in-app via halaman Pengaturan disimpan pada tabel `telegram_settings` (admin only), token tidak pernah dirender, Tes Koneksi mengirim pesan tes beneran; alert row commit SEBELUM kirim Telegram; kirim via stdlib urllib, tanpa dependensi baru.
  - Review menemukan bug desain counter basi (bukan salah eksekusi): diperbaiki dengan reset counter di check_now / edit / toggle sebelum merge.
  - Terverifikasi live: DOWN alert x2 + PULIH alert, semua terkonfirmasi in-app + Telegram, tanpa duplikat, cleanup bersih.
- Fase 5.3 Grafik riwayat uptime & response time (main `2d950c1`, migrasi 018):
  - Tabel uptime_checks: tiap cek (scheduler, Check All, Cek Now, edit re-check, add) menulis tepat satu baris; cleanup otomatis baris > 30 hari di run_all_checks(); cascade app-level saat monitor dihapus.
  - Halaman Riwayat per monitor: grafik latensi SVG server-rendered (tanpa library JS / CDN) + 6 statistik (uptime %, rata-rata / min / maks latensi, total cek, jumlah DOWN); rentang 24 jam (titik mentah) / 7 hari / 30 hari (bucket per jam).
  - Terverifikasi live: monitor UP (Total 3, Uptime 100%, polyline), monitor DOWN (Total 1, Uptime 0%, titik merah baseline), fallback range=bogus → 24 jam, cleanup bersih.
- Fase 5.3-fix Statistik 7d/30d (main `f0c0368`):
  - Min/Maks/Avg latensi 7d/30d kini memakai agregat mentah (MIN/MAX/SUM), bukan lagi min/maks dari rata-rata per jam.
  - Terverifikasi live di monitor Portfolio: 24j min 38 / maks 122 / avg 74,6 = 7h/30h min 38,0 / maks 122,0 / avg 74,6.

## [2026-10-15] - Fase 3: Asset Management
- Pengelolaan siklus hidup aset dengan status pengadaan (*asset lifecycle*) (PR #31, main `37572c4`):
  - Penambahan status baru `Procurement` pada aset sehingga daftar status lengkap menjadi `Procurement`, `Active`, `Under Repair`, dan `Retired` (`ALLOWED_STATUSES`).
  - Penyesuaian filter status antarmuka, formulir tambah/edit aset, dan lencana status pada tabel serta halaman detail aset.
- Penugasan aset ke pengguna (*asset assignment*) (PR #32, main `2f182f2`):
  - Penambahan kolom `assigned_to VARCHAR(50)` pada tabel `assets` melalui migrasi Alembic `010_add_asset_assigned_to.py` dan `init_db()`.
  - Dukungan penugasan perangkat kepada pengguna dengan peran `admin`, `it`, atau `user` (mengecualikan `guest`), dilengkapi filter penugasan pada daftar aset (`unassigned` atau spesifik pengguna).
- Informasi dan pengingat masa garansi aset (*warranty reminders*) (PR #33, main `4e151b5`):
  - Penambahan kolom `purchase_date DATE` dan `warranty_expiry DATE` pada tabel `assets` melalui migrasi Alembic `011_add_asset_warranty_dates.py` dan `init_db()`.
  - Validasi tanggal berformat YYYY-MM-DD dengan aturan `warranty_expiry` tidak boleh sebelum `purchase_date`.
  - Tampilan sisa hari garansi pada detail aset serta kalkulasi status garansi dinamis (*Aktif — habis dalam N hari*, *Habis hari ini*, atau *Sudah habis — N hari lalu*).
- Penegasan status tanpa garansi (*explicit Tanpa Garansi*) dan reposisi antarmuka (PR #34, main `b7169f7`; PR #36):
  - Penambahan kolom `no_warranty BOOLEAN DEFAULT FALSE` pada tabel `assets` melalui migrasi Alembic `012_add_asset_no_warranty.py` dan `init_db()`.
  - Checkbox "Tanpa Garansi" yang mengosongkan serta menonaktifkan input tanggal garansi habis saat dipilih (*checkbox-wins*).
  - Pemindahan letak checkbox "Tanpa Garansi" agar berada tepat di bawah input tanggal "Garansi Habis" pada formulir tambah dan edit aset (Step 3.3b, PR #36).
- Jejak audit aktivitas aset (*asset audit trail*) (PR #35, main `cd72438`):
  - Pembentukan tabel baru `asset_activities` melalui migrasi Alembic `013_add_asset_activities.py` dan `init_db()` (`id`, `asset_id`, `actor`, `action`, `field_name`, `old_value`, `new_value`, `created_at`).
  - Pencatatan linimasa aktivitas otomatis untuk aksi: `created` saat pembuatan aset, `updated` per field yang mengalami perubahan saat diedit, `soft-deleted` saat penghapusan sementara, dan `restored` saat pemulihan aset (tanpa *historical backfill* untuk data aset lama).
  - Panel "Riwayat Perubahan" pada halaman detail aset yang merender label field audit dan nilai perubahan yang mudah dibaca.
- Impor massal aset dari CSV (*bulk asset import*) (PR #36, main `80f6324`):
  - Rute baru `GET, POST /assets/import` khusus peran `admin` dan `it`.
  - Validasi ketat baris header tepat 12 kolom: `asset_tag, name, category, ip_address, mac_address, status, assigned_to, purchase_date, warranty_expiry, no_warranty, location, notes`.
  - Transaksi atomik penuh (*all-or-nothing*): jika terdapat 1 baris tidak valid, seluruh proses impor dibatalkan tanpa ada data yang tersimpan, mengumpulkan seluruh galat per baris, dan membatasi maksimal 200 baris per berkas.
  - Pencatatan entri linimasa `asset_activities` beraksi `created` untuk setiap aset yang berhasil diimpor dalam transaksi database yang sama.
- Template CSV unduhan dan perapian kotak panduan impor (PR #37, main `576f82d`):
  - Rute baru `GET /assets/import/template` khusus peran `admin` dan `it` yang menghasilkan berkas CSV siap pakai secara *in-memory* dengan nama berkas `template_import_aset.csv`.
  - Berkas template memuat header 12 kolom dan tepat 1 baris contoh data valid (`CONTOH-001`).
  - Redesain kotak dokumentasi format pada `/assets/import` dalam bahasa Indonesia terstruktur (Cara Import, Ketentuan, dan Header CSV) dengan proteksi `overflow-wrap: break-word` dan `word-break: break-all` agar baris header tidak meluap (*overflow*).
- Halaman cetak label QR fisik aset (PR #38, main `202272d`):
  - Rute baru `GET /assets/<int:asset_id>/label` untuk peran `admin`, `it`, dan `guest` (visibilitas baca sama dengan detail aset).
  - Pembangkitan kode QR secara *server-side* menggunakan pustaka `qrcode==8.2` dan `Pillow`, dikonversi *in-memory* melalui `io.BytesIO` menjadi data URI base64 tanpa menulis berkas fisik ke disk.
  - Muatan (*payload*) QR berupa URL lengkap halaman detail aset via `url_for('assets.detail', asset_id=asset_id, _external=True)`.
  - Template cetak mandiri (`templates/assets/label.html`) dengan tombol aksi "Cetak" (`window.print()`) yang disembunyikan otomatis pada media cetak (`@media print`).
- Dukungan *reverse proxy* via Werkzeug ProxyFix (PR #39, main `d25a23f`):
  - Pemasangan middleware `ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)` pada `app.py` agar aplikasi mempercayai header `X-Forwarded-*` dari Nginx (tepat 1 *hop*).
  - Memastikan `url_for(..., _external=True)` pada payload QR menghasilkan URL berskema `https://` yang sesuai dengan akses peramban pengguna.
  - *Catatan prasyarat*: ProxyFix hanya berdampak jika *reverse proxy* (Nginx) meneruskan skema protokol asli melalui header `X-Forwarded-Proto` (konfigurasi sisi server di luar repositori).

## [2026-10-15] - Blok "Besok" + susulan
- Penambahan notifikasi polling tiket baru pada daftar Service Desk (PR #27):
  - Endpoint baru `GET /tickets/api/new-count` khusus peran `admin` dan `it` yang mengembalikan jumlah tiket baru sejak baseline `since_id` pengguna dalam format JSON `{"new_count": N, "latest_id": M}` dengan filter status, assignee, dan pencarian yang identik dengan rute daftar tiket.
  - Skrip polling inline pada halaman daftar tiket (`/tickets/`) yang melakukan pengecekan setiap 30 detik hanya saat tab peramban aktif (`document.visibilityState === 'visible'`) tanpa tumpang tindih permintaan (*request overlap guard*).
  - Banner tunggal berpenanda `🔔 N tiket baru` dengan tombol `Muat tiket baru` (memuat ulang halaman dengan filter yang sama) berstandar touch-height 44px; disembunyikan secara bawaan dan ditampilkan via kelas CSS tanpa inline style. Peran `guest` dan `user` tidak memuat skrip maupun banner polling.
- Penambahan profile dropdown dan konfirmasi logout (PR #28):
  - Penggantian tautan teks pengguna dan logout di header menjadi satu tombol dropdown profil (#profile-button) berisi menu Ganti Password dan tombol form POST Logout.
  - Perubahan rute logout menjadi POST-only (`POST /logout`); akses langsung melalui metode GET mengembalikan status HTTP 405 Method Not Allowed.
  - Generalisasi modal konfirmasi bersama (`_confirm_modal.html`) menggunakan atribut `data-confirm-label` dengan nilai bawaan `"Ya, Hapus"` untuk form hapus yang telah ada dan label khusus `"Ya, Keluar"` pada form logout.
  - Penutupan otomatis dropdown profil saat form logout dikirimkan sebelum modal konfirmasi terbuka.
- Batch deploy guard, session timeout, dan perapian header (PR #29):
  - Penambahan concurrency guard pada workflow GitHub Actions `.github/workflows/deploy.yml` (`concurrency: group: deploy-production, cancel-in-progress: false`) untuk mencegah race condition deploy ganda ke server produksi; deploy kedua akan mengantre tanpa membatalkan deploy yang sedang berjalan.
  - Penegakan batas kedaluwarsa sesi tidak aktif 30 menit (*30-minute idle session timeout*) melalui konfigurasi `PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)` dan `SESSION_REFRESH_EACH_REQUEST = True` pada `app.py`, serta penetapan `session.permanent = True` pada alur login berhasil di `routes/auth.py`.
  - Perapian tampilan header di `templates/base.html`: tombol profil disederhanakan dengan indikator chevron `▾` yang berotasi via atribut `aria-expanded`, pemindahan badge peran ke baris header dropdown non-klik bertuliskan "Masuk sebagai", penyelarasan hover tombol hamburger, serta penyesuaian tata letak mobile (baris 1: hamburger & tombol profil, baris 2: judul halaman penuh).

## [2026-10-14] - Fase 2: Service Desk lanjutan
- Penambahan relasi tiket dengan auto-close tiket duplikat (PR #21, Step 2.5):
  - Tabel baru `ticket_relationships` melalui migrasi Alembic `008_add_ticket_relationships.py` dan `init_db()`.
  - Penautan tiket lain sebagai "related" (tautan biasa) atau "duplicate" oleh peran Admin dan IT.
  - Penandaan duplikat secara otomatis menutup tiket saat ini (*auto-close* dari status `Open` atau `In Progress`) dengan catatan solusi `"Duplikat dari TCK-XXX"`, pencatatan linimasa bertipe `status`, dan trigger webhook `ticket.status_changed`.
  - Konvensi penyimpanan data relasi duplikat: `ticket_a_id` sebagai tiket duplikat dan `ticket_b_id` sebagai tiket kanonikal; penegakan keunikan pasangan dua arah pada level aplikasi.
  - Tampilan daftar relasi tiket pada kedua tiket terkait; pemutusan relasi (*unlink*) tidak pernah membuka kembali tiket yang telah ditutup.
- Penambahan pustaka template respon cepat (*canned responses*) untuk komentar tiket (PR #20, Step 2.4):
  - Tabel baru `canned_responses` melalui migrasi Alembic `007_add_canned_responses.py` dan `init_db()`.
  - Antarmuka manajemen pustaka template (`/tickets/canned-responses*`) khusus Admin dan IT.
  - Menu pemilih (*picker*) template pada form komentar tiket untuk Admin/IT yang mengisi textarea via serialisasi aman `tojson | safe` tanpa pernah mengirim komentar secara otomatis (*never auto-send*).
- Penambahan fitur buka ulang tiket yang telah selesai (*reopen tickets*) (PR #19, Step 2.3):
  - Pengaktifan kembali tiket `Resolved` atau `Closed` ke status `Open` oleh pelapor tiket atau Admin/IT melalui tombol form pada halaman detail tiket.
  - Mengosongkan kolom penyelesaian (`resolved_by`, `resolved_at`, `resolution_note`) namun mempertahankan penugasan (*assignee*) serta riwayat rating CSAT sebelumnya.
  - Alasan buka ulang opsional (maksimal 500 karakter), pencatatan aktivitas bertipe `status`, dan pengiriman notifikasi webhook `ticket.status_changed`.
  - Perhitungan SLA tetap berjalan mengacu pada waktu pembuatan awal (`created_at`).
- Penambahan penilaian kepuasan pelanggan (*CSAT rating*) pada tiket selesai (PR #18, Step 2.2):
  - Tabel baru `ticket_ratings` melalui migrasi Alembic `006_add_ticket_ratings.py` dan `init_db()`.
  - Formulir penilaian bintang 1–5 dan komentar ulasan opsional (maksimal 1000 karakter) khusus bagi pelapor tiket pada tiket `Resolved` atau `Closed` (guest ditolak).
  - Mekanisme *upsert* (`ON CONFLICT (ticket_id) DO UPDATE`) yang memungkinkan pelapor memperbarui penilaian yang telah dikirim.
- Penambahan modul Knowledge Base: fondasi, pencarian/filter, dan artikel terkait (PR #15, #16, #17, Step 2.1a/b/c):
  - Tabel baru `kb_articles` melalui migrasi Alembic `005_add_knowledge_base.py` dan `init_db()`.
  - Modul Blueprint baru `knowledge_base` (`/knowledge-base/`) untuk pembuatan, pengubahan, dan penghapusan artikel oleh Admin dan IT.
  - Visibilitas artikel berbasis peran: artikel `published` dapat diakses seluruh peran; artikel `draft` hanya dapat diakses Admin/IT (mengembalikan 404 bagi peran lain untuk mencegah kebocoran informasi).
  - Pencarian artikel dengan kata kunci (parameterized `ILIKE`) dan filter dropdown kategori tiket.
  - Tampilan hingga 5 artikel solusi berstatus `published` dari kategori yang sama pada halaman detail tiket Service Desk.
- Perbaikan cascade delete pada penghapusan permanen tiket (Sweep PR #22, Commit `ef862ad`):
  - Penghapusan otomatis data terkait pada `ticket_ratings` dan `ticket_relationships` di dalam transaksi yang sama saat tiket dihapus permanen oleh Admin.
  - Migrasi data satu kali melalui Alembic `009_delete_orphan_ratings_and_relationships.py` untuk membersihkan data yatim (*orphan rows*) dari penghapusan tiket uji coba sebelumnya.
- Rangkaian tindak lanjut dan pengerasan Fase 1 (*Fase 1 follow-ups & hardening*):
  - Pengerasan Service Desk (PR #12): penguncian tiket selesai dari modifikasi status biasa atau komentar/lampiran baru, validasi integritas staf penugasan (*assignee*), serta penghapusan berkas fisik dan riwayat aktivitas saat tiket dihapus permanen.
  - Persistensi berkas unggahan: konfigurasi volume mount host Docker (`/home/ubuntu/my-web-app-uploads` ↔ `/app/uploads`) untuk menjaga keutuhan berkas lampiran saat redeploy container.
  - Penyesuaian batas unggahan Nginx: konfigurasi `client_max_body_size 15m` pada reverse proxy (aplikasi tetap membatasi 5 MB per berkas).
  - Penataan antarmuka antrean tiket (PR #13 & PR #14): penataan lencana status bertumpuk vertikal tepat di atas lencana SLA secara terpusat tanpa tumpang-tindih visual, serta perataan tengah (*text-align: center*) pada header dan seluruh sel kolom STATUS tabel tiket.

## [2026-10-13] - Fase 1: Service Desk inti
- Penambahan lampiran berkas (*file attachments*) untuk tiket Service Desk:
  - Tabel baru `ticket_attachments` melalui migrasi Alembic `004_add_ticket_attachments.py` dan `init_db()`.
  - Penyimpanan berkas di filesystem (`uploads/`, dikonfigurasi via `UPLOAD_FOLDER`) dengan nama acak UUID untuk mencegah kerentanan path traversal.
  - Batasan server-side: maksimal 2 berkas per tiket, maksimal 5 MB per berkas, serta allowlist ekstensi dokumen, gambar, dan log.
  - Kompresi gambar otomatis menggunakan Pillow ke format JPEG (maksimal 1920px, kualitas 70); berkas GIF dan dokumen disimpan apa adanya (*as-is*).
  - Akses unduh terproteksi otorisasi peran via rute `send_file` (`as_attachment=True`).
- Penambahan notifikasi webhook generik (*generic webhook notifications*) untuk Service Desk:
  - Pengiriman HTTP POST JSON ke URL webhook (`WEBHOOK_URL`) saat tiket dibuat (`ticket.created`), status berubah (`ticket.status_changed`), dan penugasan diperbarui (`ticket.assigned`).
  - Desain fail-open sinkron dengan timeout maksimal 5 detik menggunakan pustaka standar Python `urllib` (tanpa dependensi eksternal).
  - Dipicu setelah transaksi basis data di-commit; kegagalan webhook tidak mempengaruhi atau menggagalkan operasi tiket.
  - Notifikasi email secara eksplisit ditunda (*deferred*).
- Penambahan target dan peringatan SLA (*SLA targets & warnings*) pada modul Service Desk:
  - Target respon dan resolusi otomatis berbasis prioritas: Critical (1h/4h), High (2h/8h), Medium (4h/24h), Low (8h/72h).
  - Evaluasi status SLA otomatis (*state machine*): 'SLA Terpenuhi' (hijau), 'Mendekati SLA' (kuning), dan 'SLA Terlewati' (merah).
  - Perhitungan waktu berjalan dinamis tanpa modifikasi skema maupun migrasi basis data.
- Penambahan fitur komentar dan riwayat aktivitas tiket (*ticket comments & activity history*):
  - Tabel baru `ticket_activities` melalui migrasi Alembic `003_add_ticket_activities.py` dan `init_db()`.
  - Form komentar pada detail tiket untuk role `admin`, `it`, dan `user` (pada tiket miliknya sendiri).
  - Pencatatan otomatis peristiwa tiket: pembuatan (`created`), perubahan status (`status`), dan penugasan (`assignment`).
  - Linimasa aktivitas terpadu terurut dari yang terbaru (*newest-first*) dengan proteksi escaping bawaan Jinja2.
- Penambahan fitur penugasan tiket (*ticket assignment*):
  - Kolom `assigned_to` pada tabel `tickets` melalui migrasi Alembic `002_add_ticket_assigned_to.py` dan `init_db()`.
  - Form penugasan tiket untuk role `admin` dan `it` pada halaman detail tiket, serta tampilan teks assignee untuk semua role.
  - Kolom Assignee pada tabel tiket serta filter dropdown `?assignee=` (`all`, `unassigned`, `me`).
- Eksekusi otomatis migrasi basis data Alembic saat container dijalankan (*auto-run migrations on container start*) via `entrypoint.sh` sebelum aplikasi Flask berjalan.
- Inisiasi fondasi dokumentasi proyek di direktori `docs/` (`README.md`, `architecture.md`, `setup.md`, `features.md`).

## [2026-10-13] - Asset Restore
- **Commit**: `af09147`
- **Deskripsi**: Menambahkan fungsionalitas pemulihan (*restore*) untuk aset yang telah di-soft-delete kembali ke inventaris aktif:
  - Rute baru `POST /assets/restore/<int:asset_id>` dengan otorisasi role `admin` dan `it`.
  - Mengembalikan status `is_deleted = FALSE`, mengosongkan cap waktu dan alasan hapus, serta memperbarui `updated_by`.
  - Tombol aksi "Restore" pada tabel `deleted_history.html` dan halaman `deleted_detail.html`.

## [2026-10-13] - Reports Resize Fix
- **Commit**: `5641d9a`
- **Deskripsi**: Memperbaiki masalah resizing pada kartu laporan Service Desk dengan membuat kolom grid filter tanggal lebih fleksibel (`grid-template-columns: repeat(auto-fit, minmax(...))`).

## [2026-10-13] - Reports Align Fix
- **Commit**: `b1c35c1`
- **Deskripsi**: Memperbaiki tinggi kartu laporan yang tidak seragam pada tampilan desktop dengan menetapkan `align-items: stretch` pada container grid laporan.

## [2026-10-12 - 2026-10-13] - Fase 0 Mobile Responsiveness
- **Commits**:
  - `8a1cade` (2026-10-13): Task 5h - Perbaikan tata letak halaman kelola (departments, categories) untuk perangkat mobile.
  - `9848afa` (2026-10-13): Task 5g - Pembungkus tabel riwayat aset terhapus (`table-responsive`) untuk tampilan mobile.
  - `9d475f2`, `c8288ed` (2026-10-13): Task 5f - Penyesuaian media query dan grid kartu laporan pada layar kecil.
  - `2bb1231` (2026-10-13): Task 5e - Perbaikan responsivitas tabel manajemen pengguna.
  - `6b3dd4c`, `d75aea8` (2026-10-13): Task 5d - Perbaikan responsivitas tabel monitor uptime.
  - `994a717` (2026-10-13): Task 5c - Pembungkus kontainer responsif pada tabel service desk tickets.
  - `77771c8`, `181f6f1` (2026-10-12): Penataan tombol aksi header aset dan tabel inventaris aktif.
  - `70b189f` (2026-10-12): Implementasi shell dasar responsif mobile (navigasi off-canvas sidebar, tombol hamburger, backdrop, dan target sentuh minimal 44px).
