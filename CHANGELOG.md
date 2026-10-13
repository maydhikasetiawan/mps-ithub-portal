# Changelog

Semua perubahan penting pada proyek **MPS-ITHub Portal** didokumentasikan dalam berkas ini. Format penulisan mengacu pada prinsip Keep a Changelog.

---

## [Unreleased]
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
