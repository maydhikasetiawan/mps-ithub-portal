# Changelog

Semua perubahan penting pada proyek **MPS-ITHub Portal** didokumentasikan dalam berkas ini. Format penulisan mengacu pada prinsip Keep a Changelog.

---

## [Unreleased]

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
