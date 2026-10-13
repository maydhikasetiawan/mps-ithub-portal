# MPS-ITHub Portal

**MPS-ITHub Portal** adalah platform portal operasional teknologi informasi internal yang dirancang untuk mengintegrasikan inventaris aset & IPAM (*IP Address Management*), sistem tiket helpdesk (*Service Desk*), pemantauan ketersediaan server dan layanan secara waktu nyata (*Uptime Monitor*), pusat pelaporan dan ekspor data, serta administrasi pengguna berbasis peran (*Role-Based Access Control*).

## Teknologi Utama (Tech Stack)
- **Backend & Web**: Python 3.11, Flask 3.0.2, Werkzeug 3.0.1, Jinja2
- **Tampilan Antarmuka**: Vanilla Custom CSS (tanpa framework CSS eksternal)
- **Basis Data & Migrasi**: PostgreSQL (`psycopg2-binary`), Alembic
- **Kontainer & Deployment**: Docker, GitHub Actions CI/CD, AWS EC2

## Dokumentasi Teknis
Seluruh panduan teknis dan spesifikasi sistem tersedia di direktori `docs/`:
- **[Indeks Dokumentasi](docs/README.md)** — Ringkasan dan panduan navigasi dokumen.
- **[Arsitektur Sistem](docs/architecture.md)** — Tumpukan teknologi, modul Blueprint, skema tabel basis data, dan pipeline CI/CD.
- **[Panduan Setup Lokal](docs/setup.md)** — Prasyarat, variabel lingkungan yang digunakan kode, migrasi, dan langkah menjalankan aplikasi.
- **[Inventaris Fitur & Hak Akses](docs/features.md)** — Daftar fitur per modul dan tabel matriks peran pengguna.

## Cara Menjalankan Aplikasi
Pasang dependensi menggunakan `pip install -r requirements.txt`, siapkan variabel lingkungan basis data PostgreSQL di file `.env`, lalu eksekusi `python app.py` (aplikasi aktif di `http://localhost:5000`). Rincian lengkap langkah konfigurasi dan verifikasi tersedia di **[Panduan Setup Lokal](docs/setup.md)**.

## Catatan Perubahan
Riwayat pengembangan dan catatan rilis terdokumentasi di **[CHANGELOG.md](CHANGELOG.md)**.
