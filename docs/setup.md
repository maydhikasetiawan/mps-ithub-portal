# Panduan Menjalankan Aplikasi Secara Lokal (Setup Guide)

Panduan ini menjelaskan langkah-langkah menyiapkan dan menjalankan **MPS-ITHub Portal** di lingkungan pengembangan lokal (*local development*).

---

## 1. Prasyarat Sistem (Prerequisites)

- **Python**: Versi 3.11 atau lebih baru
- **PostgreSQL**: Server PostgreSQL aktif (lokal atau melalui Docker)
- **Git**: Untuk manajemen repositori
- **Virtual Environment**: Modul `venv` bawaan Python

---

## 2. Mengklon Repositori

```bash
git clone https://github.com/maydhikasetiawan/mps-ithub-portal.git
cd mps-ithub-portal
```

---

## 3. Variabel Lingkungan (Environment Variables)

Sistem membaca konfigurasi lingkungan melalui variabel sistem (*environment variables*). Berikut seluruh variabel yang dirujuk langsung dalam kode sumber:

| Nama Variabel | Lokasi Penggunaan dalam Kode | Deskripsi & Nilai Bawaan |
| --- | --- | --- |
| `SECRET_KEY` | `app.py` (baris 14) | Kunci rahasia penandatanganan sesi Flask. Aplikasi akan memicu *RuntimeError* jika variabel ini belum disetel. |
| `DB_HOST` | `database/db.py` (baris 7), `migrations/env.py` (baris 15) | Hostname / alamat IP server PostgreSQL (contoh: `localhost`). |
| `DB_NAME` | `database/db.py` (baris 8), `migrations/env.py` (baris 16) | Nama basis data PostgreSQL (contoh: `db_monitoring`). |
| `DB_USER` | `database/db.py` (baris 9), `migrations/env.py` (baris 17) | Pengguna basis data (contoh: `admin_server`). |
| `DB_PASS` | `database/db.py` (baris 10), `migrations/env.py` (baris 18) | Kata sandi pengguna basis data. |
| `DB_PORT` | `migrations/env.py` (baris 19) | Port koneksi basis data untuk runner Alembic (opsional, default: `'5432'`). Pada koneksi utama `database/db.py`, port 5432 digunakan secara langsung. |
| `API_KEY` | `routes/api.py` | Kunci rahasia bersama untuk autentikasi endpoint REST API v1 (`/api/v1/*`). Harus berupa string acak yang kuat (disimpan sebagai GitHub Secrets `API_KEY` saat deployment). Mengadopsi prinsip *fail-closed*: jika variabel ini tidak disetel atau header `X-API-Key` salah/hilang, permintaan API akan ditolak dengan status HTTP 401. |
| `WEBHOOK_URL` | `routes/tickets.py` | URL receiver webhook outbound; kosong = pengiriman dilewati (tidak ada percobaan pengiriman). |
| `UPTIME_CHECK_INTERVAL` | `routes/uptime.py` | Interval scheduler pengecekan uptime dalam detik (default: 300). |

Salin template berkas `.env.example` ke `.env`:
```bash
cp .env.example .env
```
Lalu lengkapi nilai variabel sesuai kredensial server PostgreSQL lokal Anda.

---

## 4. Inisialisasi Basis Data & Migrasi (DB Init & Migrations)

1. **Persiapan Database**:
   Pastikan basis data target telah dibuat di instance PostgreSQL Anda:
   ```sql
   CREATE DATABASE db_monitoring;
   ```

2. **Inisialisasi Tabel Awal**:
   Jalankan `alembic upgrade head` — Alembic membuat SEMUA tabel (tabel dasar di migrasi `001`, seed kategori di `020`). Tidak ada akun seed; akun admin pertama dibuat via `psql` (lihat §7).

3. **Menjalankan Migrasi Skema (Alembic)**:
   Eksekusi migrasi untuk membentuk SEMUA tabel (satu perintah, sama seperti §2):
   ```bash
   alembic upgrade head
   ```

---

## 5. Cara Menjalankan Aplikasi

1. **Buat dan Aktifkan Virtual Environment**:
   - Di Linux/macOS:
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```
   - Di Windows (PowerShell):
     ```powershell
     python -m venv venv
     .\venv\Scripts\Activate.ps1
     ```

2. **Pasang Dependensi**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set Variabel Lingkungan & Jalankan Server**:
   Jika menggunakan terminal tanpa pembaca otomatis `.env`:
   - Di Linux/macOS:
     ```bash
     export SECRET_KEY="kunci-rahasia-lokal"
     export DB_HOST="localhost"
     export DB_NAME="db_monitoring"
     export DB_USER="postgres"
     export DB_PASS="password_anda"
     python app.py
     ```
   - Di Windows (PowerShell):
     ```powershell
     $env:SECRET_KEY="kunci-rahasia-lokal"
     $env:DB_HOST="localhost"
     $env:DB_NAME="db_monitoring"
     $env:DB_USER="postgres"
     $env:DB_PASS="password_anda"
     python app.py
     ```

Server akan aktif dan mendengarkan permintaan pada `http://0.0.0.0:5000`.

> [!NOTE]
> **Catatan Produksi**: Perintah `python app.py` hanya digunakan untuk pengembangan lokal (*local development*). Di lingkungan produksi, aplikasi dijalankan menggunakan server WSGI Gunicorn 26.2.0 melalui `entrypoint.sh` di dalam container Docker (lihat rincian pada `docs/architecture.md`).

---

## 6. Verifikasi Instalasi

1. **Uji Sintaks Python**:
   Jalankan pemeriksaan kompilasi untuk memastikan integritas kode:
   ```bash
   python -m py_compile app.py routes/*.py database/db.py
   ```
   Perintah harus selesai tanpa menampilkan galat (*exit code 0*).

2. **Verifikasi Melalui Peramban (Browser Check)**:
   - Buka `http://localhost:5000/health`: Memastikan API hidup dengan respon JSON `{"status": "healthy"}` (HTTP 200).
   - Buka `http://localhost:5000`: Halaman akan otomatis diarahkan ke `/login`.
   - Masuk menggunakan akun admin yang kamu buat via `psql` (lihat §2 / §7).
   - Pastikan halaman beralih ke Dasbor Operasional dengan metrik aktif.

---

## 7. Fresh Deploys & Schema Management

- **Fresh Deploys**: `alembic upgrade head` creates ALL tables (base tables in `001`, seeds in `020`) — `init_db()` no longer exists.
- **Admin Account**: The first admin account is NOT seeded. Create it via `psql` with a strong password hashed via `generate_password_hash` (e.g. `<choose-a-strong-password>`).
- **Seed Accounts Removed**: The old `init_db` seed accounts are removed and must not be reused.
