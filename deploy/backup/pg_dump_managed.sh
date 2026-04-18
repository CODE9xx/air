#!/usr/bin/env bash
# =============================================================================
# Code9 Analytics — PostgreSQL backup для managed Postgres (Timeweb и т.п.)
#
# Отличия от pg_dump.sh:
#   - БД внешняя (не docker-контейнер), подключаемся через POSTGRES_HOST/PORT.
#   - pg_dump / pg_dumpall запускаются через одноразовый контейнер postgres:18-alpine
#     с --network host (чтобы видеть приватный IP managed БД из хостовой сети).
#   - PGPASSWORD передаётся в окружение контейнера (не в argv → не светится в ps).
#
# Cron:
#   0 3 * * *  /opt/code9-analytics/deploy/backup/pg_dump_managed.sh >> /var/log/code9-backup.log 2>&1
#
# Retention: 14 дней rolling, + offsite (Sprint 2).
# =============================================================================
set -euo pipefail

# --- Параметры ------------------------------------------------------------
PROJECT_DIR="${PROJECT_DIR:-/opt/code9-analytics}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/code9}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
PG_IMAGE="${PG_IMAGE:-postgres:18-alpine}"

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

: "${POSTGRES_HOST:?POSTGRES_HOST is required (private IP managed Postgres)}"
: "${POSTGRES_PORT:?POSTGRES_PORT is required (usually 5432)}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"

# --- Подготовка директории -------------------------------------------------
mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%d_%H%M%SZ)"
OUT_FILE="$BACKUP_DIR/code9_${STAMP}.sql.gz"
GLOBALS_FILE="$BACKUP_DIR/code9_globals_${STAMP}.sql.gz"
TMP_FILE="${OUT_FILE}.tmp"
TMP_GLOBALS="${GLOBALS_FILE}.tmp"

echo "[backup] starting — ${STAMP}"
echo "[backup]   host      → ${POSTGRES_HOST}:${POSTGRES_PORT}"
echo "[backup]   db        → ${OUT_FILE}"
echo "[backup]   globals   → ${GLOBALS_FILE}"

# --- 1. globals-only через pg_dumpall -------------------------------------
# NB: На Timeweb managed Postgres у gen_user может НЕ быть прав на pg_authid
# (superuser-only). В этом случае pg_dumpall --globals-only вернёт частичный дамп
# или ошибку. Это НЕ критично для restore drill на том же кластере (роли уже есть),
# но важно для full DR на чистой VPS → см. docs/deploy/INSTALL_TIMEWEB.md §"Backup".
docker run --rm \
    --network host \
    -e PGPASSWORD="$POSTGRES_PASSWORD" \
    "$PG_IMAGE" \
    pg_dumpall \
        --host="$POSTGRES_HOST" \
        --port="$POSTGRES_PORT" \
        --username="$POSTGRES_USER" \
        --globals-only \
        --no-role-passwords \
    | gzip -9 > "$TMP_GLOBALS" || {
        echo "[backup] WARN pg_dumpall --globals-only вернул non-zero (возможно, нет прав superuser)" >&2
        echo "[backup] WARN сохраняем как есть, проверь содержимое вручную" >&2
    }

mv "$TMP_GLOBALS" "$GLOBALS_FILE"
chmod 600 "$GLOBALS_FILE"

GLOBALS_SIZE="$(du -h "$GLOBALS_FILE" | cut -f1)"
echo "[backup] OK globals — ${GLOBALS_FILE} (${GLOBALS_SIZE})"

# --- 2. pg_dump: содержимое БД (все схемы, включая tenant_*) --------------
docker run --rm \
    --network host \
    -e PGPASSWORD="$POSTGRES_PASSWORD" \
    "$PG_IMAGE" \
    pg_dump \
        --host="$POSTGRES_HOST" \
        --port="$POSTGRES_PORT" \
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

# --- Ротация --------------------------------------------------------------
find "$BACKUP_DIR" -maxdepth 1 \( -name 'code9_*.sql.gz' -o -name 'code9_globals_*.sql.gz' \) \
    -type f -mtime "+${RETAIN_DAYS}" -print -delete

# --- TODO Sprint 2: offsite upload ----------------------------------------
# rclone copy "$OUT_FILE"     offsite:code9-backups/  || echo "[backup] WARN offsite upload failed"
# rclone copy "$GLOBALS_FILE" offsite:code9-backups/  || echo "[backup] WARN offsite globals upload failed"

echo "[backup] done"
