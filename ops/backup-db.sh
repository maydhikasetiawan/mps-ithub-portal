#!/usr/bin/env bash
#
# backup-db.sh — backup otomatis database MPSHub (Fase 9.1)
#
# pg_dump database db_monitoring dari dalam container PostgreSQL,
# streaming ke gzip -1, retensi 7 dump harian + 4 snapshot mingguan
# (hari Senin), alert Telegram HANYA saat gagal, upload offsite
# Backblaze B2 opsional (nonaktif secara default).
#
# Konfigurasi: skrip ini me-source /etc/mpshub/backup.env bila ada
# (chmod 600, berisi token/chat id/rclone bila dipakai). Semua nilai
# bisa di-override lewat environment; TIDAK ada rahasia di file ini.
#
# Cron (server diasumsikan zona Asia/Jakarta) — TANPA redirect:
# skrip menulis log-nya sendiri ke $LOG_FILE, redirect cron ke file
# yang sama akan menggandakan setiap baris log.
#
#   15 2 * * * /opt/mpshub/ops/backup-db.sh
#
# Panduan lengkap (instalasi, restore, troubleshooting):
# docs/backups.md di repo ini.

set -euo pipefail

# ---------------------------------------------------------------------------
# Konfigurasi
# ---------------------------------------------------------------------------
ENV_FILE="${ENV_FILE:-/etc/mpshub/backup.env}"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

PG_CONTAINER="${PG_CONTAINER:-postgres-server}" # nama container PostgreSQL
PG_DB="${PG_DB:-db_monitoring}"                  # database yang di-backup
PG_USER="${PG_USER:-admin_server}"               # role pg_dump di server
PG_PASSWORD="${PG_PASSWORD:-}"                   # kosong = auth container
BACKUP_DIR="${BACKUP_DIR:-/var/backups/mpshub}"  # root direktori backup
RETENTION_DAILY="${RETENTION_DAILY:-7}"          # dump harian yang disimpan
RETENTION_WEEKLY="${RETENTION_WEEKLY:-4}"        # snapshot mingguan disimpan
LOG_FILE="${LOG_FILE:-/var/log/mpshub/backup-db.log}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"     # kosong = alert nonaktif
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"
B2_ENABLED="${B2_ENABLED:-0}"                    # 1 = upload offsite aktif
B2_REMOTE="${B2_REMOTE:-b2:mpshub-backups}"      # remote rclone
B2_PREFIX="${B2_PREFIX:-daily/}"

DAILY_DIR="$BACKUP_DIR/daily"
WEEKLY_DIR="$BACKUP_DIR/weekly"
LOCK_FILE="$BACKUP_DIR/backup-db.lock"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="$DAILY_DIR/${PG_DB}_${STAMP}.dump.gz"

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
log()  { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"; }
die()  { log "ERROR: $*"; send_telegram "❌ backup-db GAGAL: $*"; exit 1; }

send_telegram() {
    # Alert kegagalan via Telegram; diam bila token/chat belum dikonfigurasi.
    if [[ -n "$TELEGRAM_BOT_TOKEN" && -n "$TELEGRAM_CHAT_ID" ]]; then
        curl -fsS -m 15 -X POST \
            "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            --data-urlencode "text=$1" >/dev/null 2>&1 || \
            log "WARN: gagal mengirim alert Telegram"
    fi
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "perintah '$1' tidak ditemukan"
}

# ---------------------------------------------------------------------------
# Lock — cegah dua proses backup jalan bersamaan.
# Tabrakan lock BUKAN kegagalan: catat lalu keluar dengan tenang
# (tanpa alert Telegram), agar run yang tertahan tidak dianggap gagal.
# ---------------------------------------------------------------------------
mkdir -p "$DAILY_DIR" "$WEEKLY_DIR" "$(dirname "$LOG_FILE")"
chmod 700 "$BACKUP_DIR" 2>/dev/null || true
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "SKIP: lock $LOCK_FILE sedang dipakai — backup sebelumnya belum selesai"
    exit 0
fi

log "=== mulai backup ${PG_DB} (${STAMP}) ==="
if [[ -z "$TELEGRAM_BOT_TOKEN" || -z "$TELEGRAM_CHAT_ID" ]]; then
    log "WARN: alert Telegram nonaktif (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID kosong)"
fi

# ---------------------------------------------------------------------------
# Pra-pemeriksaan (ringan, penting untuk EC2 RAM 909 MiB)
# ---------------------------------------------------------------------------
need_cmd docker; need_cmd gzip; need_cmd flock; need_cmd curl; need_cmd df
docker inspect -f '{{.State.Running}}' "$PG_CONTAINER" 2>/dev/null | grep -q true \
    || die "container '$PG_CONTAINER' tidak berjalan"

FREE_KB="$(df -k -P "$BACKUP_DIR" | awk 'NR==2 {print $4}')"
[[ "$FREE_KB" -ge 1048576 ]] || die "ruang bebas < 1 GiB di $BACKUP_DIR (${FREE_KB} KiB)"

# ---------------------------------------------------------------------------
# Dump: pg_dump -Fc dari DALAM container -> gzip -1 streaming (hemat RAM)
# ---------------------------------------------------------------------------
log "menjalankan pg_dump dari container '$PG_CONTAINER'..."
run_dump() {
    if [[ -n "$PG_PASSWORD" ]]; then
        docker exec -e PGPASSWORD="$PG_PASSWORD" "$PG_CONTAINER" \
            pg_dump -U "$PG_USER" -d "$PG_DB" -Fc --no-owner --no-privileges
    else
        docker exec "$PG_CONTAINER" \
            pg_dump -U "$PG_USER" -d "$PG_DB" -Fc --no-owner --no-privileges
    fi
}
# Dibungkus if agar kegagalan dump memicu die() (alert Telegram + cleanup),
# bukan berhenti diam-diam karena set -e / pipefail.
if ! run_dump | gzip -1 -c > "$OUT_FILE.tmp"; then
    rm -f "$OUT_FILE.tmp"
    die "pg_dump gagal untuk database '$PG_DB'"
fi

# Validasi: file harus ada, tidak kosong, dan gzip valid.
[[ -s "$OUT_FILE.tmp" ]] || die "hasil dump kosong"
gzip -t "$OUT_FILE.tmp" || die "file dump rusak (gzip test gagal)"
SIZE="$(du -h "$OUT_FILE.tmp" | cut -f1)"
mv "$OUT_FILE.tmp" "$OUT_FILE"
log "dump OK: $OUT_FILE ($SIZE)"

# ---------------------------------------------------------------------------
# Promosi mingguan (hari Senin) + rotasi retensi
# ---------------------------------------------------------------------------
if [[ "$(date +%u)" == "1" ]]; then
    cp "$OUT_FILE" "$WEEKLY_DIR/$(basename "$OUT_FILE")"
    log "disalin ke weekly (hari Senin)"
fi

prune() { # prune <dir> <keep>
    local dir="$1" keep="$2" n=0 f
    while IFS= read -r f; do
        n=$((n+1))
        if [[ "$n" -gt "$keep" ]]; then rm -f "$f"; log "hapus lama: $(basename "$f")"; fi
    done < <(ls -t "$dir"/*.dump.gz 2>/dev/null)
}
prune "$DAILY_DIR" "$RETENTION_DAILY"
prune "$WEEKLY_DIR" "$RETENTION_WEEKLY"

# ---------------------------------------------------------------------------
# Offsite ke Backblaze B2 (SEKSI TERPISAH — nonaktif secara default)
# ---------------------------------------------------------------------------
if [[ "$B2_ENABLED" == "1" ]]; then
    need_cmd rclone
    [[ -n "$B2_REMOTE" ]] || die "B2_REMOTE kosong padahal B2 dinyalakan"
    log "upload offsite ke $B2_REMOTE/$B2_PREFIX ..."
    rclone copyto "$OUT_FILE" "${B2_REMOTE}/${B2_PREFIX}$(basename "$OUT_FILE")" \
        || die "upload offsite gagal"
    log "upload offsite OK"
else
    log "offsite B2: nonaktif (set B2_ENABLED=1 untuk menyalakan)"
fi

log "=== backup selesai OK ==="
