#!/usr/bin/env bash
# =============================================================================
# Code9 Analytics — PostgreSQL backup script
#
# Рекомендуется запускать через cron ежедневно ночью:
#   0 3 * * *  /opt/code9-analytics/deploy/backup/pg_dump.sh >> /var/log/code9-backup.log 2>&1
#
# Retention: 14 дней rolling, + вручную копии на offsite storage
# =============================================================================
set -euo pipefail

# --- Параметры ------------------------------------------------------------
PROJECT_DIR="${PROJECT_DIR:-/opt/code9-analytics}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/code9}"
COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_DIR}/deploy/docker-compose.prod.yml}"
SERVICE="${SERVICE:-postgres}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"

# --- Загружаем env --------------------------------------------------------
ENV_FILE="${ENV_FILE:-${PROJECT_DIR}/.env.production}"
if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "[backup] FATAL: env file not found: $ENV_FILE" >&2
    exit 1
fi

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"

# --- Подготовка директории -------------------------------------------------
mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%d_%H%M%SZ)"
OUT_FILE="$BACKUP_DIR/code9_${STAMP}.sql.gz"
GLOBALS_FILE="$BACKUP_DIR/code9_globals_${STAMP}.sql.gz"
TMP_FILE="${OUT_FILE}.tmp"
TMP_GLOBALS="${GLOBALS_FILE}.tmp"

echo "[backup] starting — ${STAMP}"
echo "[backup]   db        → ${OUT_FILE}"
echo "[backup]   globals   → ${GLOBALS_FILE}"

# --- 1. pg_dumpall --globals-only: роли, tablespaces, настройки кластера ---
# Без этого дампа при переезде на новый сервер потерялись бы роли/права.
# Файл небольшой (< 10 KB), держим рядом с основным дампом.
docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" \
    pg_dumpall \
        --username="$POSTGRES_USER" \
        --globals-only \
        --no-role-passwords \
    | gzip -9 > "$TMP_GLOBALS"

mv "$TMP_GLOBALS" "$GLOBALS_FILE"
chmod 600 "$GLOBALS_FILE"

GLOBALS_SIZE="$(du -h "$GLOBALS_FILE" | cut -f1)"
echo "[backup] OK globals — ${GLOBALS_FILE} (${GLOBALS_SIZE})"

# --- 2. pg_dump: содержимое БД code9 (все схемы, включая tenant_*) ---------
# pg_dump -Fc (custom format) был бы компактнее, но plain text + gzip удобнее
# для diff и быстрой проверки. Для больших БД переключиться на -Fc.
docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" \
    pg_dump \
        --username="$POSTGRES_USER" \
        --dbname="$POSTGRES_DB" \
        --no-owner \
        --no-privileges \
        --clean --if-exists \
        --format=plain \
    | gzip -9 > "$TMP_FILE"

mv "$TMP_FILE" "$OUT_FILE"
chmod 600 "$OUT_FILE"

SIZE="$(du -h "$OUT_FILE" | cut -f1)"
echo "[backup] OK db      — ${OUT_FILE} (${SIZE})"

# --- Ротация старых бэкапов -----------------------------------------------
# Удаляем и основной дамп, и globals (идут в паре)
find "$BACKUP_DIR" -maxdepth 1 \( -name 'code9_*.sql.gz' -o -name 'code9_globals_*.sql.gz' \) \
    -type f -mtime "+${RETAIN_DAYS}" -print -delete

# --- TODO Sprint 2: offsite upload ----------------------------------------
# rclone copy "$OUT_FILE"     offsite:code9-backups/  || echo "[backup] WARN offsite upload failed"
# rclone copy "$GLOBALS_FILE" offsite:code9-backups/  || echo "[backup] WARN offsite globals upload failed"

echo "[backup] done"
