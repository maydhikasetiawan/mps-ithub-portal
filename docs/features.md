# Inventaris Fitur & Matriks Hak Akses (Features & Roles Matrix)

Dokumen ini memuat inventaris fitur lengkap **MPS-ITHub Portal** beserta matriks hak akses (*Role-Based Access Control / RBAC*) yang didasarkan pada dekorator dan logika otorisasi pada kode sumber.

---

## 1. Inventaris Fitur per Modul

### A. Modul Autentikasi (`routes/auth.py`)
- **Login Sesi**: Akses masuk berbasis username dan hash kata sandi (`Werkzeug`).
- **Proteksi Brute-Force**: Membatasi kegagalan login maksimal 5 kali dalam 15 menit per kombinasi IP dan username; mengembalikan kode HTTP 429 saat terkunci.
- **Logout Sesi**: Menghapus seluruh data sesi dan mengembalikan pengguna ke halaman login.
- **Enforcement Ganti Kata Sandi**: Pengalihan otomatis bagi akun dengan status `must_change_password = TRUE`.

### B. Modul Dasbor Operasional (`routes/dashboard.py`)
- **Statistik Aset Aktif**: Perhitungan total aset yang tidak berstatus terhapus (`is_deleted = FALSE`).
- **Statistik Tiket Aktif**: Perhitungan tiket dengan status `Open` atau `In Progress`.
- **Persentase Ketersediaan Layanan**: Perhitungan rasio layanan berstatus `UP` dari tabel monitor.

### C. Modul IT Assets / IPAM (`routes/assets.py`)
- **Daftar Inventaris Aset**: Menampilkan seluruh perangkat aktif dengan kalkulasi umur perangkat otomatis.
- **Pencarian Aset**: Pencarian fleksibel berdasarkan nama, tag aset, IP, atau lokasi.
- **Tambah Aset**: Pendaftaran perangkat baru dengan validasi keunikan tag aset (*asset tag*).
- **Detail & Spesifikasi**: Informasi rinci perangkat keras, alamat IP, alamat MAC, dan riwayat pembaruan.
- **Ubah Aset**: Pembaruan data jaringan, status, lokasi, dan catatan teknis.
- **Soft Delete Aset**: Pemindahan aset ke riwayat terhapus dengan pencatatan alasan dan pengguna yang menghapus.
- **Restore Aset**: Mengembalikan aset terhapus ke daftar aktif via form POST instan.
- **Riwayat Terhapus**: Halaman arsip untuk meninjau aset-aset yang telah dihapus sementara.
- **Hard Delete (Hapus Permanen)**: Penghapusan total dari database khusus Admin dengan konfirmasi nama aset dan kata sandi.

### D. Modul Service Desk (`routes/tickets.py`)
- **Daftar Tiket**: Menampilkan antrean tiket bantuan. Pengguna reguler (`user`) hanya melihat tiket miliknya sendiri.
- **Buat Tiket**: Form pembuatan tiket masalah dengan penomoran otomatis (`TCK-YYYYMMDD-XXX`).
- **Detail Tiket**: Rincian permasalahan, data pelapor, dan departemen pelapor.
- **Penyelesaian Masalah**: Pembaruan status pengerjaan tiket dan input laporan solusi (*resolution note*). Tiket berstatus `Resolved` atau `Closed` dikunci dari modifikasi lebih lanjut.
- **Kategori Tiket Dinamis**: Penambahan dan penghapusan kategori tiket oleh Administrator.
- **Hapus Permanen Tiket**: Penghapusan data tiket dari database dengan konfirmasi kata sandi Admin.

### E. Modul Uptime Monitor (`routes/uptime.py`)
- **Daftar Monitor Jaringan**: Monitoring status ketersediaan target (`UP` / `DOWN`) beserta waktu latensi (*latency* dalam milidetik).
- **Tambah Target Monitor**: Penambahan endpoint baru dengan pilihan protokol TCP Socket atau HTTP Request, disertai uji kesehatan instan.
- **Pindai Ulang Mandiri (Check Now)**: Trigger uji kesehatan langsung untuk target tertentu.
- **Pindai Seluruh Layanan (Check All)**: Trigger uji kesehatan sekaligus ke seluruh daftar target monitor.
- **Hapus Target Monitor**: Menghapus target dari daftar pemantauan.

### F. Modul Reports Center (`routes/reports.py`)
- **Ekspor CSV Aset TI**: Unduh berkas CSV dengan filter kategori, status, dan opsi menyertakan aset terhapus.
- **Ekspor CSV Service Desk**: Unduh berkas CSV tiket dengan filter rentang tanggal, kategori, dan status tiket.
- **Kompatibilitas Excel**: Berkas CSV disandikan dengan format UTF-8-SIG (`\ufeff`) agar kolom dan pemisah terbaca rapi pada Microsoft Excel.

### G. Modul User Management & Profil (`routes/users.py`)
- **Daftar Pengguna**: Menampilkan seluruh data akun, peran, dan departemen terkait.
- **Tambah Pengguna**: Pendaftaran akun baru dengan hashing kata sandi aman.
- **Edit Pengguna & Reset Password**: Pembaruan data akun serta opsi reset kata sandi administratif (mengaktifkan flag wajib ganti password).
- **Hapus Pengguna**: Penghapusan akun dengan penjaga (*guard*) keamanan mencegah penghapusan akun diri sendiri yang sedang aktif.
- **Manajemen Departemen**: Tambah dan hapus departemen organisasi (penghapusan ditolak jika masih terdapat pengguna di departemen tersebut).
- **Ganti Kata Sandi Mandiri**: Fasilitas pembaruan kata sandi oleh masing-masing pengguna dengan validasi kata sandi lama.

---

## 2. Matriks Hak Akses (Roles Matrix)

Matriks berikut didasarkan langsung pada dekorator `@roles_required`, `@login_required`, serta kontrol akses di tingkat rute dan template:

| Modul | Fitur / Tindakan | Endpoint & Method | `admin` | `it` | `user` | `guest` | Dasar Grounding Kode |
| --- | --- | --- | :---: | :---: | :---: | :---: | --- |
| **Auth** | Login & Logout | `/login`, `/logout` [GET, POST] | Ya | Ya | Ya | Ya | Rute publik / sesi |
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
| **Tickets** | Daftar Tiket | `/tickets/` [GET] | Ya | Ya | Ya* | Ya | `@roles_required('admin', 'it', 'user', 'guest')` (*user: hanya tiket sendiri) |
| | Buat Tiket Baru | `/tickets/add` [GET, POST] | Ya | Ya | Ya | Tidak | `@roles_required('admin', 'it', 'user')` |
| | Detail Tiket | `/tickets/<id>` [GET] | Ya | Ya | Ya* | Ya | `@roles_required('admin', 'it', 'user', 'guest')` (*user: hanya tiket sendiri) |
| | Update Status & Solusi | `/tickets/<id>` [POST] | Ya | Ya | Tidak | Tidak | Logika controller rute: role dibatasi ke `admin` dan `it` |
| | Kelola Kategori Tiket | `/tickets/categories` [GET, POST] | Ya | Tidak | Tidak | Tidak | `@roles_required('admin')` |
| | Hapus Kategori Tiket | `/tickets/categories/delete/<id>` [GET] | Ya | Tidak | Tidak | Tidak | `@roles_required('admin')` |
| | Hapus Tiket Permanen | `/tickets/delete-permanent/<id>` [GET, POST] | Ya | Tidak | Tidak | Tidak | `@roles_required('admin')` |
| **Uptime** | Daftar Monitor | `/uptime/` [GET] | Ya | Ya | Tidak | Ya | `@roles_required('admin', 'it', 'guest')` |
| | Tambah Monitor | `/uptime/add` [GET, POST] | Ya | Ya | Tidak | Tidak | `@roles_required('admin', 'it')` |
| | Pindai Target (Single/All) | `/uptime/check/<id>`, `/check-all` [GET] | Ya | Ya | Tidak | Ya | `@roles_required('admin', 'it', 'guest')` |
| | Hapus Monitor | `/uptime/delete/<id>` [GET] | Ya | Ya | Tidak | Tidak | `@roles_required('admin', 'it')` |
| **Reports** | Halaman Laporan & Ekspor | `/reports/`, `/reports/export/*` [GET] | Ya | Ya | Ya** | Ya** | `@login_required` (**menu navbar disembunyikan untuk `user` & `guest`) |
| **Users** | Kelola Akun Pengguna | `/users/`, `/add`, `/edit/*`, `/delete/*` | Ya | Tidak | Tidak | Tidak | `@roles_required('admin')` |
| | Kelola Departemen | `/users/departments*` [GET, POST] | Ya | Tidak | Tidak | Tidak | `@roles_required('admin')` |
