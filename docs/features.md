# Inventaris Fitur & Matriks Hak Akses (Features & Roles Matrix)

Dokumen ini memuat inventaris fitur lengkap **MPS-ITHub Portal** beserta matriks hak akses (*Role-Based Access Control / RBAC*) yang didasarkan pada dekorator dan logika otorisasi pada kode sumber.

---

## 1. Inventaris Fitur per Modul

### A. Modul Autentikasi (`routes/auth.py`)
- **Login Sesi**: Akses masuk berbasis username dan hash kata sandi (`Werkzeug`).
- **Proteksi Brute-Force**: Membatasi kegagalan login maksimal 5 kali dalam 15 menit per kombinasi IP dan username; mengembalikan kode HTTP 429 saat terkunci.
- **Logout Sesi**: Form POST khusus dengan modal konfirmasi interaktif ("Keluar dari aplikasi?") melalui dropdown profil di header; menghapus seluruh data sesi dan mengembalikan pengguna ke halaman login (rute `POST /logout` menolak metode GET dengan 405 Method Not Allowed).
- **Idle Session Timeout (30 Menit)**: Sesi kedaluwarsa otomatis setelah 30 menit tanpa aktivitas (*server-side rolling idle timeout* melalui `PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)` dan `SESSION_REFRESH_EACH_REQUEST = True`). Permintaan berikutnya setelah kedaluwarsa dialihkan kembali ke halaman login dengan notifikasi satu kali bahwa sesi telah berakhir; pesan tidak muncul bagi pengunjung baru pertama kali maupun setelah aksi logout yang disengaja.
- **Profile Dropdown**: Menu dropdown pengguna pada header (#profile-button) yang menampilkan nama pengguna, chevron rotasi, header status peran ("Masuk sebagai"), tautan Ganti Password, dan aksi Logout.
- **Enforcement Ganti Kata Sandi**: Pengalihan otomatis bagi akun dengan status `must_change_password = TRUE`.

### B. Modul Dasbor Operasional (`routes/dashboard.py`)
- **Statistik Aset Aktif**: Perhitungan total aset yang tidak berstatus terhapus (`is_deleted = FALSE`).
- **Statistik Tiket Aktif**: Perhitungan tiket dengan status `Open` atau `In Progress`.
- **Persentase Ketersediaan Layanan**: Perhitungan rasio layanan berstatus `UP` dari tabel monitor.
- **Grafik Analitis SVG Server-Rendered**: 4 grafik server-rendered SVG (grafik harian "Tiket Baru — 30 Hari Terakhir" / `daily_chart_svg`, tiket per kategori, tiket per status, dan aset per status) yang menggunakan palet warna Fase 5.3 tanpa dependensi script/CDN eksternal.
- **Tabel Garansi Akan Habis**: Tabel HTML kondisional yang merinci perangkat dengan garansi mendekati habis (tampil hanya jika terdapat data aset relevan).
- **Tren Komparasi 30 Hari**: Statistik komparasi tiket dibuat dan diselesaikan (30 hari berjalan vs 30 hari sebelumnya) diturunkan langsung dari data tanpa migrasi basis data.

### C. Modul IT Assets / IPAM (`routes/assets.py`)
- **Daftar Inventaris Aset**: Menampilkan seluruh perangkat aktif dengan kalkulasi umur perangkat otomatis, paginasi (20 data per halaman dengan pembatasan halaman dan navigasi nomor), filter status (`Procurement`, `Active`, `Under Repair`, `Retired`), dan filter penugasan (`unassigned` atau spesifik pengguna).
- **Pencarian Aset**: Pencarian fleksibel berdasarkan nama, tag aset, IP, atau lokasi.
- **Tambah Aset**: Pendaftaran perangkat baru dengan validasi keunikan tag aset (*asset tag*), nomor seri perangkat (`serial_number`), kategori (Server, PC/Laptop, Network, Docker Container, Printer/Peripherals), status, penugasan pengguna, tanggal beli, dan tanggal garansi habis.
- **Detail & Spesifikasi**: Informasi rinci perangkat keras, nomor seri perangkat (`serial_number`), alamat IP, alamat MAC, status penugasan, status masa garansi dinamis, dan kalkulasi usia perangkat.
- **Pengingat & Manajemen Garansi**: Validasi tanggal beli (`purchase_date`) dan habis garansi (`warranty_expiry`), opsi eksplisit **Tanpa Garansi** (`no_warranty`) yang menonaktifkan input tanggal habis garansi saat dicentang, serta indikator status garansi dinamis pada halaman detail aset.
- **Jejak Audit Aktivitas Aset (Riwayat Perubahan)**: Linimasa pencatatan perubahan pada detail aset yang melacak aksi pembuatan (`created`), pembaruan per kolom data (`updated`), penghapusan sementara (`soft-deleted`), dan pemulihan (`restored`) melalui tabel `asset_activities`.
- **Ubah Aset**: Pembaruan data perangkat keras, nomor seri perangkat (`serial_number`), penugasan, garansi, status, lokasi, dan catatan teknis dengan audit pencatatan perubahan otomatis.
- **Impor Massal Aset via CSV**: Fitur impor massal hingga 200 baris per berkas melalui `/assets/import` menggunakan template 13 kolom (dengan `serial_number` bersifat opsional; berkas CSV lama 12 kolom tetap diterima) dan transaksi atomik (*all-or-nothing*). Dilengkapi fasilitas pengunduhan berkas template CSV siap pakai (`/assets/import/template`).
- **Cetak Label QR Fisik**: Halaman cetak stiker label QR perangkat (`/assets/<id>/label`) dengan pembangkitan kode QR *server-side* (menghasilkan URL detail aset ber-HTTPS via ProxyFix) dan format siap cetak yang otomatis menyembunyikan tombol cetak pada media cetak.
- **Soft Delete Aset**: Pemindahan aset ke riwayat terhapus dengan pencatatan alasan dan pengguna yang menghapus.
- **Restore Aset**: Mengembalikan aset terhapus ke daftar aktif via form POST instan.
- **Riwayat Terhapus**: Halaman arsip untuk meninjau aset-aset yang telah dihapus sementara.
- **Hard Delete (Hapus Permanen)**: Penghapusan total dari database khusus Admin dengan konfirmasi nama aset dan kata sandi.

### D. Modul Service Desk (`routes/tickets.py`)
- **Daftar Tiket**: Menampilkan antrean tiket bantuan dengan paginasi (20 data per halaman dengan pembatasan halaman dan navigasi nomor). Pengguna reguler (`user` dan `guest`) hanya melihat tiket miliknya sendiri; badge status ditumpuk vertikal tepat di atas badge SLA secara terpusat, dan header beserta sel kolom STATUS rata tengah (*centered*).
- **Buat Tiket**: Form pembuatan tiket masalah dengan penomoran otomatis (`TCK-YYYYMMDD-XXX`).
- **Detail Tiket**: Rincian permasalahan, data pelapor, departemen pelapor, meta tanggal pembuatan dan pembaruan ("Dibuat: <created_at> | Terakhir diperbarui: <last_updated>" berbasis linimasa aktivitas terbaru dengan fallback `created_at`), serta baris "Diselesaikan oleh" yang hanya tampil bila `resolved_at` terisi (dengan fallback `-` jika resolver kosong).
- **Penugasan Tiket (Assign Ticket)**: Penugasan tiket kepada staf IT atau Admin tertentu serta opsi mengosongkan penugasan (*Unassigned*).
- **Penyelesaian Masalah**: Pembaruan status pengerjaan tiket dan input laporan solusi (*resolution note*). Tiket berstatus `Resolved` atau `Closed` dikunci dari modifikasi lebih lanjut.
- **Komentar Tiket**: Penambahan catatan komunikasi atau komentar oleh Admin, IT, maupun pelapor (User pada tiket miliknya).
- **Riwayat Aktivitas (Timeline)**: Pencatatan kronologis terpadu untuk pembuatan tiket, perubahan status, penugasan, komentar, unggah lampiran berkas (`attachment`), pemberian rating CSAT (`rating`), dan pembaruan catatan penyelesaian tiket saja (`note`).
- **Target & Peringatan SLA**: Perhitungan target waktu respon dan resolusi otomatis berbasis prioritas (Critical, High, Medium, Low) dengan indikator status otomatis (*SLA Terpenuhi*, *Mendekati SLA*, *SLA Terlewati*).
- **Notifikasi Webhook**: Pengiriman notifikasi HTTP POST asinkron berformat JSON ke URL eksternal (`WEBHOOK_URL`) saat tiket dibuat (`ticket.created`), status berubah (`ticket.status_changed`), atau penugasan diperbarui (`ticket.assigned`). Pengiriman diantrekan secara non-blocking dengan pencatatan log pengiriman ke tabel `webhook_deliveries`, diproses via background daemon thread dengan mekanisme coba ulang (*retry*) hingga 3 kali (backoff 2s, 4s). Penambahan komentar tidak memicu webhook, dan notifikasi email ditunda (*deferred*).
- **Lampiran Berkas (Attachments)**: Fasilitas unggah berkas pendukung pada pembuatan dan detail tiket (maksimal 2 berkas per tiket, batas 5 MB per berkas; gambar, dokumen, log). Gambar dikompresi otomatis ke format JPEG (maksimal 1920px, kualitas 70 via Pillow), dan berkas dilindungi otorisasi saat diunduh. Penyimpanan berkas persisten melalui Docker volume mount host (`/home/ubuntu/my-web-app-uploads` ↔ `/app/uploads`), didukung konfigurasi Nginx `client_max_body_size 15m`.
- **Penilaian Kepuasan (CSAT)**: Satu penilaian per tiket (bintang 1–5, komentar opsional maks 1000 karakter) oleh pelapor tiket pada tiket berstatus `Resolved` atau `Closed`. Pengiriman ulang memperbarui penilaian yang ada (*upsert*); peran `guest` ditolak.
- **Buka Ulang Tiket (Reopen)**: Pelapor atau Admin/IT dapat membuka kembali tiket `Resolved` atau `Closed` ke status `Open` dengan alasan opsional (maks 500 karakter). Mengosongkan data penyelesaian (`resolved_by`, `resolved_at`, `resolution_note`) namun tetap mempertahankan penugasan (*assignee*) dan rating CSAT sebelumnya; mencatat aktivitas bertipe `status` dan memicu webhook `ticket.status_changed`; perhitungan SLA tetap mengacu pada `created_at` awal.
- **Template Respon Cepat (Canned Responses)**: Pustaka template balasan tiket yang dikelola oleh Admin/IT (judul, konten, kategori opsional, pembuat). Menu pemilih (*picker*) pada form komentar mengisi teks ke textarea (khusus Admin/IT); template tidak pernah mengirim otomatis (*never auto-send*), pengguna selalu meninjau, mengedit, dan mengirim komentar secara manual.
- **Relasi Tiket & Auto-Close Duplikat (Ticket Relationships)**: Admin/IT dapat menghubungkan tiket sebagai "related" (tautan biasa) atau "duplicate". Penandaan duplikat secara otomatis menutup tiket saat ini (hanya jika berstatus `Open` atau `In Progress`) dengan catatan solusi `"Duplikat dari TCK-XXX"`, pencatatan aktivitas status, dan pengiriman webhook `ticket.status_changed`. Pemutusan relasi (*unlink*) tidak pernah membuka kembali tiket yang telah ditutup; daftar relasi tampil pada kedua tiket.
- **Notifikasi Polling Tiket Baru**: Pengecekan tiket baru berkala (setiap 30 detik pada tab aktif) bagi Admin dan IT melalui endpoint `GET /tickets/api/new-count` dengan parameter filter aktif; menampilkan banner notifikasi `🔔 N tiket baru` dan tombol `Muat tiket baru` untuk memuat ulang daftar tiket dengan filter yang sama.
- **Kategori Tiket Dinamis**: Penambahan dan penghapusan kategori tiket oleh Administrator.
- **Hapus Permanen Tiket**: Penghapusan total data tiket dari basis data khusus Admin dengan konfirmasi kata sandi; otomatis menghapus aktivitas, lampiran berkas (+ berkas fisik), penilaian CSAT, dan relasi tiket untuk mencegah data yatim (*no orphans*).

### E. Modul Knowledge Base (`routes/knowledge_base.py`)
- **Manajemen Artikel Pengetahuan**: CRUD artikel solusi teknis (judul, konten, kategori, tag, status draft/published) oleh Admin dan IT.
- **Visibilitas Berbasis Peran**: Artikel `published` dapat diakses seluruh pengguna (termasuk `guest`); artikel `draft` hanya dapat diakses Admin dan IT (mengembalikan HTTP 404 bagi peran lain untuk mencegah kebocoran informasi).
- **Pencarian & Filter Kategori**: Pencarian artikel pada halaman daftar menggunakan kata kunci (parameterized `ILIKE`) serta filter dropdown berdasarkan kategori tiket.
- **Artikel Terkait pada Tiket**: Menampilkan hingga 5 artikel berstatus `published` dari kategori yang sama pada halaman detail tiket Service Desk ("Artikel Knowledge Base Terkait").

### F. Modul Uptime Monitor (`routes/uptime.py`)
- **Daftar Monitor Jaringan**: Monitoring status ketersediaan target (`UP` / `DOWN`) beserta waktu latensi (*latency* dalam milidetik).
- **Tambah Target Monitor**: Penambahan endpoint baru dengan pilihan protokol TCP Socket atau HTTP Request, disertai uji kesehatan instan.
- **Pindai Ulang Mandiri (Check Now)**: Trigger uji kesehatan langsung untuk target tertentu.
- **Pindai Seluruh Layanan (Check All)**: Trigger uji kesehatan sekaligus ke seluruh daftar target monitor.
- **Hapus Target Monitor**: Menghapus target dari daftar pemantauan.
- **Pengecekan Otomatis Terjadwal**: Scheduler in-app memeriksa monitor yang aktif dengan interval dari variabel lingkungan `UPTIME_CHECK_INTERVAL` (default 300 detik).
- **Toggle Pemantauan Otomatis**: Nyalakan/matikan pengecekan otomatis per monitor; monitor nonaktif tampil NONAKTIF + baris redup.
- **Ubah Target Monitor**: Ubah nama/target/tipe/port monitor beserta re-check instan saat monitor aktif.
- **Alert DOWN / PULIH**: Alert transisi status di Riwayat Alert halaman Uptime + Telegram; DOWN setelah 2 cek DOWN otomatis berurutan dengan flag `is_alerted` (mencegah duplikasi DOWN akibat reset counter; alert PULIH hanya dikirim jika flag `is_alerted` aktif); banner DOWN saat ada layanan mati.
- **Pengaturan Telegram (Admin)**: Simpan bot token + chat ID via halaman Pengaturan (token tidak pernah dirender); Tes Koneksi mengirim pesan tes beneran.
- **Riwayat & Grafik per Monitor**: Halaman Riwayat dengan grafik latensi + statistik (uptime %, rata-rata/min/maks latensi, total cek, jumlah DOWN); rentang 24 jam / 7 hari / 30 hari; retensi 30 hari.

### G. Modul Reports Center (`routes/reports.py`)
- **Ekspor CSV Aset TI**: Unduh berkas CSV dengan filter kategori, status, dan opsi menyertakan aset terhapus. Memuat header block (judul, tanggal dibuat laporan, pembuat laporan, filter), summary block (total aset, rincian status dan kategori), 18 kolom detail termasuk 4 kolom baru: `Serial Number`, `Assigned To`, `Purchase Date`, dan `Warranty Expiry`, serta footer total baris data (`Total Baris Data: N`).
- **Ekspor CSV Service Desk**: Unduh berkas CSV tiket dengan filter rentang tanggal, kategori, dan status tiket. Memuat header block (judul, tanggal dibuat laporan, pembuat laporan, periode, filter), summary block (total tiket, rincian status, prioritas, kategori, rata-rata durasi penyelesaian, % SLA terpenuhi, rata-rata CSAT), 17 kolom detail termasuk 5 kolom baru: `Assignee`, `SLA`, `Durasi Penyelesaian`, `CSAT`, dan `Terakhir Diperbarui`, serta footer total baris data (`Total Baris Data: N`).
- **Kompatibilitas Excel**: Berkas CSV disandikan dengan format UTF-8-SIG (`\ufeff`) agar kolom dan pemisah terbaca rapi pada Microsoft Excel.

### H. Modul User Management & Profil (`routes/users.py`)
- **Daftar Pengguna**: Menampilkan seluruh data akun, peran, dan departemen terkait.
- **Tambah Pengguna**: Pendaftaran akun baru dengan hashing kata sandi aman.
- **Edit Pengguna & Reset Password**: Pembaruan data akun serta opsi reset kata sandi administratif (mengaktifkan flag wajib ganti password).
- **Hapus Pengguna (Soft Delete)**: Penghapusan akun beralih ke soft delete dengan pencatatan alasan penghapusan serta penjaga (*guard*) keamanan mencegah penghapusan akun diri sendiri yang sedang aktif. Akun terhapus dicegah login dan kueri operasional memfilter `is_deleted = FALSE`.
- **Riwayat User Terhapus & Pemulihan**: Halaman riwayat pengguna terhapus (`/users/deleted-history`) dengan fitur pencarian, halaman detail akun terhapus, pemulihan akun (*restore*), dan penghapusan permanen (*hard delete*) khusus Admin dengan konfirmasi ganda (ketik username + kata sandi admin).
- **Manajemen Departemen**: Tambah dan hapus departemen organisasi (penghapusan ditolak jika masih terdapat pengguna di departemen tersebut).
- **Ganti Kata Sandi Mandiri**: Fasilitas pembaruan kata sandi oleh masing-masing pengguna dengan validasi kata sandi lama.
- **Jejak Audit Aktivitas User**: Linimasa pencatatan seluruh mutasi akun user dan departemen ke dalam tabel `user_activities` (11 tipe event: `user_created`, `user_soft_deleted`, `user_restored`, `user_hard_deleted`, `department_created`, `department_deleted`, `role_changed`, `password_reset`, `email_changed`, `department_changed`, `password_changed`), tersimpan langsung di basis data (DB-only, tanpa antarmuka pengguna).

### I. Modul REST API v1 (`routes/api.py`, prefix `/api/v1`)
- **API Read-Only**: Endpoint `GET` terpusat untuk integrasi data tiket bantuan, aset TI, dan monitor layanan tanpa izin operasi tulis (`POST`/`PUT`/`DELETE`).
- **Autentikasi Header API Key**: Autentikasi kunci tunggal dari variabel lingkungan `API_KEY` via header `X-API-Key` dengan verifikasi *constant-time* (`hmac.compare_digest`) dan fail-closed 401 saat tidak diset atau salah.
- **Paginasi & Filter**: Parameter paginasi standar (`limit` default 20 max 100, `offset` default 0), filter exact-match status/kategori/prioritas/assignee, otomatis mengecualikan entitas soft-deleted, serta pemetaan kolom tabel riil `monitors`. Referensi lengkap: [docs/API.md](API.md).

### J. Tema & Antarmuka (UI Theme)

- **Dua tema tampilan**: Tema gelap (bawaan) dan tema terang untuk seluruh aplikasi termasuk halaman login, diganti lewat tombol toggle di header; pilihan pengguna tersimpan otomatis di peramban (`localStorage`).
- **Tampilan responsif**: Navigasi sidebar menjadi drawer pada layar kecil; tabel data berubah menjadi kartu berlabel pada lebar ≤620px; target sentuh minimal 44px.
- **Animasi antarmuka**: Animasi masuk halaman/kartu, modal, dan dropdown dengan durasi singkat (150–300ms), otomatis nonaktif bila pengguna mengaktifkan *reduced motion* di sistemnya.

---

## 2. Matriks Hak Akses (Roles Matrix)

Matriks berikut didasarkan langsung pada dekorator `@roles_required`, `@login_required`, serta kontrol akses di tingkat rute dan template:

| Modul | Fitur / Tindakan | Endpoint & Method | `admin` | `it` | `user` | `guest` | Dasar Grounding Kode |
| --- | --- | --- | :---: | :---: | :---: | :---: | --- |
| **Auth** | Login | `/login` [GET, POST] | Ya | Ya | Ya | Ya | Rute publik / login form |
| | Logout Sesi | `/logout` [POST] | Ya | Ya | Ya | Ya | `@auth_bp.route('/logout', methods=['POST'])` via profile dropdown |
| **Profil** | Ganti Password Mandiri | `/users/change-password` [GET, POST] | Ya | Ya | Ya | Ya | `@login_required` |
| **Dashboard**| Ringkasan Operasional | `/`, `/dashboard` [GET] | Ya | Ya | Ya | Ya | `@login_required` |
| **Assets** | Daftar Aset Aktif | `/assets/` [GET] | Ya | Ya | Tidak | Ya | `@roles_required('admin', 'it', 'guest')` |
| | Tambah Aset | `/assets/add` [GET, POST] | Ya | Ya | Tidak | Tidak | `@roles_required('admin', 'it')` |
| | Detail Aset | `/assets/<id>` [GET] | Ya | Ya | Tidak | Ya | `@roles_required('admin', 'it', 'guest')` |
| | Edit Aset | `/assets/edit/<id>` [GET, POST] | Ya | Ya | Tidak | Tidak | `@roles_required('admin', 'it')` |
| | Soft Delete Aset | `/assets/delete/<id>` [GET, POST] | Ya | Ya | Tidak | Tidak | `@roles_required('admin', 'it')` |
| | Restore Aset | `/assets/restore/<id>` [POST] | Ya | Ya | Tidak | Tidak | `@roles_required('admin', 'it')` |
| | Riwayat Aset Terhapus | `/assets/deleted-history` [GET] | Ya | Ya | Tidak | Ya | `@roles_required('admin', 'it', 'guest')` |
| | Detail Aset Terhapus | `/assets/deleted-detail/<id>` [GET] | Ya | Ya | Tidak | Ya | `@roles_required('admin', 'it', 'guest')` |
| | Hard Delete Aset | `/assets/hard-delete/<id>` [GET, POST] | Ya | Tidak | Tidak | Tidak | `@roles_required('admin')` |
| | Impor Massal CSV | `/assets/import` [GET, POST] | Ya | Ya | Tidak | Tidak | `@roles_required('admin', 'it')` |
| | Unduh Template CSV | `/assets/import/template` [GET] | Ya | Ya | Tidak | Tidak | `@roles_required('admin', 'it')` |
| | Cetak Label QR | `/assets/<id>/label` [GET] | Ya | Ya | Tidak | Ya | `@roles_required('admin', 'it', 'guest')` |
| **Tickets** | Daftar Tiket | `/tickets/` [GET] | Ya | Ya | Ya* | Ya | `@roles_required('admin', 'it', 'user', 'guest')` (*user: hanya tiket sendiri) |
| | Cek Tiket Baru (Polling) | `/tickets/api/new-count` [GET] | Ya | Ya | Tidak | Tidak | `@roles_required('admin', 'it')` |
| | Buat Tiket Baru | `/tickets/add` [GET, POST] | Ya | Ya | Ya | Tidak | `@roles_required('admin', 'it', 'user')` |
| | Detail Tiket | `/tickets/<id>` [GET] | Ya | Ya | Ya* | Ya | `@roles_required('admin', 'it', 'user', 'guest')` (*user: hanya tiket sendiri) |
| | Penugasan Tiket (Assignee) | `/tickets/<id>` [POST] | Ya | Ya | Tidak | Tidak | Logika controller: hanya `admin` dan `it` yang dapat menetapkan `assigned_to` |
| | Update Status & Solusi | `/tickets/<id>` [POST] | Ya | Ya | Tidak | Tidak | Logika controller rute: role dibatasi ke `admin` dan `it` |
| | Komentar Tiket | `/tickets/<id>` [POST action=comment] | Ya | Ya | Ya* | Tidak | Form komentar dibatasi untuk `admin`, `it`, dan `user` (*user: hanya tiket sendiri) |
| | Riwayat Aktivitas | `/tickets/<id>` [GET] | Ya | Ya | Ya* | Ya | Linimasa tiket dapat dilihat oleh seluruh peran (*user: hanya tiket sendiri) |
| | Target & Peringatan SLA | `/tickets/`, `/tickets/<id>` [GET] | Ya | Ya | Ya* | Ya | Indikator SLA otomatis dihitung dan tampil untuk seluruh peran (*user: hanya tiket sendiri) |
| | Notifikasi Webhook | Otomatis via `WEBHOOK_URL` | Ya | Ya | Ya* | Tidak | Dipicu otomatis pada `ticket.created`, `ticket.status_changed`, `ticket.assigned` (*user: hanya saat buat tiket; email ditunda) |
| | Lampiran Berkas (Upload/Download) | `/tickets/<id>/attachments/*` | Ya | Ya | Ya* | Unduh | Unggah: `admin`, `it`, `user` (*tiket sendiri, guest dilarang); Unduh: semua peran yang berhak melihat tiket |
| | Kelola Kategori Tiket | `/tickets/categories` [GET, POST] | Ya | Tidak | Tidak | Tidak | `@roles_required('admin')` |
| | Hapus Kategori Tiket | `/tickets/categories/delete/<id>` [GET] | Ya | Tidak | Tidak | Tidak | `@roles_required('admin')` |
| | Hapus Tiket Permanen | `/tickets/delete-permanent/<id>` [GET, POST] | Ya | Tidak | Tidak | Tidak | `@roles_required('admin')` |
| | Penilaian Kepuasan (CSAT) | `/tickets/<id>` [POST action=submit_rating] | Ya* | Ya* | Ya* | Tidak | Form rating hanya untuk pelapor tiket pada tiket Resolved/Closed (*guest dilarang) |
| | Buka Ulang Tiket (Reopen) | `/tickets/<id>` [POST action=reopen] | Ya | Ya | Ya* | Tidak | Pelapor tiket (*user tiket sendiri) atau `admin`/`it` pada tiket Resolved/Closed |
| | Kelola Template Respon | `/tickets/canned-responses*` | Ya | Ya | Tidak | Tidak | `@roles_required('admin', 'it')` (delete: POST-only) |
| | Gunakan Template Respon | `/tickets/<id>` [UI Picker] | Ya | Ya | Tidak | Tidak | Picker template pada form komentar hanya tampil untuk `admin` & `it` |
| | Tautkan / Hapus Relasi Tiket | `/tickets/<id>` [POST action=link/unlink] | Ya | Ya | Tidak | Tidak | Form relasi & aksi hapus relasi dibatasi untuk `admin` & `it` |
| | Lihat Relasi Tiket | `/tickets/<id>` [GET] | Ya | Ya | Ya* | Ya | Daftar tiket terkait tampil untuk semua peran yang berhak melihat tiket |
| **Knowledge Base** | Daftar Artikel (Published) | `/knowledge-base/` [GET] | Ya | Ya | Ya | Ya | `@roles_required('admin', 'it', 'user', 'guest')` |
| | Detail Artikel (Published) | `/knowledge-base/<id>` [GET] | Ya | Ya | Ya | Ya | `@roles_required('admin', 'it', 'user', 'guest')` |
| | Detail Artikel (Draft) | `/knowledge-base/<id>` [GET] | Ya | Ya | Tidak | Tidak | Draft artikel mengembalikan 404 bagi peran non-admin/IT |
| | Kelola Artikel (CRUD) | `/knowledge-base/add`, `edit/<id>`, `delete/<id>` | Ya | Ya | Tidak | Tidak | `@roles_required('admin', 'it')` (delete: POST-only) |
| **Uptime** | Daftar Monitor | `/uptime/` [GET] | Ya | Ya | Tidak | Ya | `@roles_required('admin', 'it', 'guest')` |
| | Tambah Monitor | `/uptime/add` [GET, POST] | Ya | Ya | Tidak | Tidak | `@roles_required('admin', 'it')` |
| | Ubah Monitor | `/uptime/edit/<id>` [GET, POST] | Ya | Ya | Tidak | Tidak | `@roles_required('admin', 'it')` |
| | Toggle Pemantauan | `/uptime/toggle/<id>` [POST] | Ya | Ya | Tidak | Tidak | `@roles_required('admin', 'it')` |
| | Pindai Target (Single/All) | `/uptime/check/<id>`, `/check-all` [GET] | Ya | Ya | Tidak | Ya | `@roles_required('admin', 'it', 'guest')` |
| | Riwayat Monitor | `/uptime/<id>/history` [GET] | Ya | Ya | Tidak | Ya | `@roles_required('admin', 'it', 'guest')` |
| | Pengaturan Telegram | `/uptime/telegram-settings` [GET, POST] | Ya | Tidak | Tidak | Tidak | `@roles_required('admin')` |
| | Tes Koneksi Telegram | `/uptime/telegram-test` [POST] | Ya | Tidak | Tidak | Tidak | `@roles_required('admin')` |
| | Hapus Monitor | `/uptime/delete/<id>` [POST] | Ya | Ya | Tidak | Tidak | `@roles_required('admin', 'it')` |
| **Reports** | Halaman Laporan & Ekspor | `/reports/`, `/reports/export/*` [GET] | Ya | Ya | Ya** | Ya** | `@login_required` (**menu navbar disembunyikan untuk `user` & `guest`) |
| **Users** | Kelola Akun Pengguna | `/users/`, `/add`, `/edit/*`, `/delete/*` | Ya | Tidak | Tidak | Tidak | `@roles_required('admin')` |
| | Kelola Departemen | `/users/departments*` [GET, POST] | Ya | Tidak | Tidak | Tidak | `@roles_required('admin')` |
