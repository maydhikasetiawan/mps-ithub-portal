# Panduan Backup & Restore Database MPSHub (Fase 9.1)

Dokumen ini menjelaskan arsitektur, instalasi di server, tata cara pengujian, prosedur restore, dan troubleshooting untuk skrip backup otomatis database `ops/backup-db.sh`.

---

## 1. Ringkasan

Skrip `ops/backup-db.sh` bertugas melakukan pencadangan otomatis harian database `db_monitoring` dari dalam kontainer Docker PostgreSQL:
- **Jadwal**: Setiap malam pukul 02:15 WIB via cron (`15 2 * * *`).
- **Format**: `pg_dump -Fc` (custom format PostgreSQL) yang dialirkan langsung (*streaming*) ke `gzip -1` guna menghemat memori (RAM) server.
- **Penyimpanan**: Disimpan di direktori lokal `/var/backups/mpshub` dengan subdirektori `daily/` dan `weekly/`.
- **Retensi**: Menyimpan 7 dump harian terbaru dan 4 snapshot mingguan (diambil otomatis setiap hari Senin).
- **Pencatatan**: Log eksekusi tersimpan rapi di `/var/log/mpshub/backup-db.log`.
- **Notifikasi**: Mengirim alert ke Telegram HANYA saat terjadi kegagalan (`die`).
- **Offsite (Opsional)**: Dukungan pengunggahan cadangan ke Backblaze B2 via `rclone` (nonaktif secara default).

---

## 2. Prasyarat

Sebelum memasang di server, pastikan hal-hal berikut telah terpenuhi:
1. Docker terpasang dan pengguna sistem memiliki hak menjalankan perintah `docker exec`.
2. Kontainer PostgreSQL bernama `postgres-server` berjalan aktif (`Running`).
3. Utilitas sistem tersedia: `docker`, `gzip`, `flock`, `curl`, dan `df`.
4. Ruang penyimpanan kosong pada partisi direktori backup minimal ≥ 1 GiB.

---

## 3. Instalasi di Server

Langkah-langkah pemasangan di lingkungan produksi:

1. Salin skrip `ops/backup-db.sh` ke direktori server:
   ```bash
   sudo mkdir -p /opt/mpshub/ops
   sudo cp ops/backup-db.sh /opt/mpshub/ops/backup-db.sh
   sudo chmod +x /opt/mpshub/ops/backup-db.sh
   ```

2. Buat berkas konfigurasi lingkungan `/etc/mpshub/backup.env` dengan hak akses ketat (chmod 600):
   ```bash
   sudo mkdir -p /etc/mpshub
   sudo nano /etc/mpshub/backup.env
   sudo chmod 600 /etc/mpshub/backup.env
   ```
   Contoh isi berkas `/etc/mpshub/backup.env` (gunakan placeholder, sesuaikan dengan konfigurasi rahasia sebenarnya):
   ```bash
   TELEGRAM_BOT_TOKEN=
   TELEGRAM_CHAT_ID=
   PG_PASSWORD=
   ```
   > **Catatan**: Variabel `PG_CONTAINER` (`postgres-server`), `PG_USER` (`admin_server`), dan `PG_DB` (`db_monitoring`) sudah memiliki default bawaan yang cocok dengan server produksi sehingga jarang perlu diubah.

3. Tambahkan jadwal cron:
   ```bash
   crontab -e
   ```
   Tambahkan baris berikut persis apa adanya:
   ```cron
   15 2 * * * /opt/mpshub/ops/backup-db.sh
   ```
   > **Perhatian**: Jangan tambahkan pengalihan output seperti `>> /var/log/... 2>&1` karena skrip secara mandiri sudah menulis log ke `$LOG_FILE`. Menambahkan redirect akan menggandakan baris log.

---

## 4. Uji Manual

Jalankan skrip secara manual untuk memastikan seluruh alur bekerja tanpa kendala:
```bash
/opt/mpshub/ops/backup-db.sh
```

Periksa keluaran log dan berkas cadangan yang dihasilkan:
```bash
tail -n 20 /var/log/mpshub/backup-db.log
ls -lh /var/backups/mpshub/daily/
```
Pastikan berkas `.dump.gz` berukuran wajar dan log diakhiri dengan `=== backup selesai OK ===`.

---

## 5. Restore ke Database Scratch (Cara Aman)

Gunakan cara ini untuk memverifikasi integritas data cadangan tanpa menyentuh database operasional live.

1. Buat database scratch sementara di dalam kontainer:
   ```bash
   docker exec postgres-server createdb -U admin_server db_monitoring_restore
   ```

2. Lakukan restore dari berkas dump cadangan:
   ```bash
   gunzip -c <file>.dump.gz | docker exec -i postgres-server pg_restore -U admin_server -d db_monitoring_restore
   ```

3. Verifikasi jumlah baris pada tabel-tabel utama:
   ```bash
   docker exec -it postgres-server psql -U admin_server -d db_monitoring_restore -c "SELECT COUNT(*) FROM assets;"
   docker exec -it postgres-server psql -U admin_server -d db_monitoring_restore -c "SELECT COUNT(*) FROM tickets;"
   docker exec -it postgres-server psql -U admin_server -d db_monitoring_restore -c "SELECT COUNT(*) FROM users;"
   ```

4. Hapus database scratch setelah selesai:
   ```bash
   docker exec postgres-server dropdb -U admin_server db_monitoring_restore
   ```

---

## 6. Restore Menimpa Database Live

> ⚠️ **PERINGATAN KERAS (DESTRUKTIF)**: Prosedur ini akan menimpa dan menghapus data operasional yang berjalan saat ini! Selalu prioritaskan pengujian di database scratch terlebih dahulu, atau lakukan backup darurat sebelum menjalankan perintah ini.

Jalankan perintah berikut untuk me-restore langsung ke database `db_monitoring`:
```bash
gunzip -c <file>.dump.gz | docker exec -i postgres-server pg_restore -U admin_server -d db_monitoring --clean --if-exists
```

---

## 7. Uji Restore Berkala

Cadangan data yang tidak pernah diuji proses restore-nya bukanlah cadangan yang valid. Sangat direkomendasikan untuk melakukan uji restore ke database scratch secara berkala setiap kali terjadi rotasi snapshot mingguan (hari Senin).

---

## 8. Offsite Backblaze B2 (Opsional)

Untuk menyimpan salinan cadangan di luar server (*offsite*):
1. Konfigurasikan remote `rclone` dengan nama `b2` (ikuti panduan `rclone config` untuk Backblaze B2).
2. Setel variabel `B2_ENABLED=1` di `/etc/mpshub/backup.env`.
3. Pasang aturan *lifecycle* pada bucket B2 Anda (misal hapus berkas lebih dari 30 hari), karena skrip ini tidak melakukan pembersihan otomatis pada penyimpanan cloud.

---

## 9. Troubleshooting

- **Lock Contention (`SKIP`)**: Jika log menampilkan `SKIP: lock ... sedang dipakai`, ini berarti proses backup sebelumnya belum selesai. Ini BUKAN error dan tidak memicu alert Telegram.
- **Ruang Disk Kurang**: Skrip membutuhkan minimal ruang bebas 1 GiB. Bila disk penuh, proses dihentikan dan mengirim alert Telegram.
- **Alert Telegram Tidak Masuk**: Periksa log apakah terdapat peringatan `WARN: alert Telegram nonaktif`. Pastikan `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID` telah terisi di `/etc/mpshub/backup.env` serta server memiliki akses internet keluar ke API Telegram.
