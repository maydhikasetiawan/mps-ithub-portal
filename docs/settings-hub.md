# Hub Pengaturan (Settings Hub)

Dokumen ini menjelaskan pengelolaan pengaturan sistem terpusat melalui halaman `/settings`.
---

## 1. Daftar Modul

Halaman Hub Pengaturan mencakup modul-modul berikut:

1. **Pengaturan Branding**: Kustomisasi identitas aplikasi (nama aplikasi, tagline, URL logo, headline dan teks login, teks footer). Tersimpan pada tabel `branding_settings`. Formulir dikirim via `POST /settings/branding`.
2. **Pengaturan Telegram**: Konfigurasi bot Telegram (Chat ID dan Bot Token terenkripsi) serta pengujian koneksi bot. Tersimpan pada tabel `telegram_settings` dan `hub_settings`. Formulir dikirim via `POST /settings/telegram` dan `POST /settings/telegram-test`.
3. **Target SLA Tiket**: Konfigurasi batas waktu respon dan resolusi tiket untuk setiap prioritas (Critical, High, Medium, Low). Tersimpan di database.
4. **Integrasi Webhook**: URL endpoint webhook untuk event tiket. Tersimpan terenkripsi di database.
5. **Interval Pemantauan Uptime**: Durasi antar pengecekan layanan uptime (60 - 3600 detik). Tersimpan di database.
6. **Kunci API (API Key)**: Kunci autentikasi REST API. Tersimpan terenkripsi di database.

### Pengalihan URL Lama (Redirects)

URL lama berikut dialihkan otomatis ke `/settings` (memerlukan login admin):
- `GET /settings/branding` -> dialihkan ke `/settings`
- `GET /uptime/telegram-settings` -> dialihkan ke `/settings`
- `POST /uptime/telegram-test` -> dialihkan ke `/settings`
---

## 2. Pembuatan Kunci Enkripsi

Nilai rahasia (secret) seperti Webhook URL, API Key, dan Bot Token disimpan dalam bentuk terenkripsi menggunakan Fernet symmetric encryption.
Kunci enkripsi dikonfigurasikan melalui environment variable `SETTINGS_ENCRYPTION_KEY`. Untuk menghasilkan kunci baru, jalankan perintah berikut:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Pasang nilai output tersebut pada GitHub Secrets (`SETTINGS_ENCRYPTION_KEY`) dan environment server produksi.
---

## 3. Konsekuensi Kehilangan Kunci dan Rotasi

- **Kehilangan Kunci**: Jika nilai `SETTINGS_ENCRYPTION_KEY` hilang atau berubah tanpa backup, data rahasia yang tersimpan di database tidak dapat didekripsi. Seluruh nilai rahasia (API Key, Webhook URL, Bot Token) harus dimasukkan ulang melalui antarmuka web.
- **Rotasi Kunci**: Saat kunci enkripsi dirotasi dengan kunci baru, data terenkripsi sebelumnya tidak otomatis terkonversi. Seluruh nilai rahasia harus dimasukkan ulang setelah kunci baru diterapkan.
---

## 4. Peringatan Token Telegram

Token bot Telegram dipakai di 3 tempat:
1. Aplikasi web (portal).
2. Bot VPS (alert bot mandiri pada server).
3. Skrip backup otomatis (`ops/backup-db.sh`).

Mengubah token bot Telegram melalui aplikasi web HANYA memperbarui copy pada aplikasi web. Bot VPS dan skrip backup tetap memakai nilai lama sampai file `.env` masing-masing diperbarui secara manual di server.
