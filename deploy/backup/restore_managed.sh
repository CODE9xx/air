#!/usr/bin/env bash
# =============================================================================
# Code9 Analytics — PostgreSQL restore для managed Postgres (Timeweb и т.п.)
#
# ОСТОРОЖНО: скрипт использует дамп с --clean --if-exists → DROPает таблицы в
# целевой БД. Используй ТОЛЬКО для restore drill на staging или при реальном
# инциденте.
#
# Usage:
#   ./deploy/backup/restore_managed.sh /var/backups/code9/code9_20260418_030000Z.sql.gz
#
# SCOPE (Gate A / Sprint 0):
#   Восстанавливается ТОЛЬКО main DB dump. Globals не применяется автоматически.
#   На managed Postgres (Timeweb) ты и так не имеешь прав superuser для
#   CREATE ROLE / ALTER SYSTEM — globals-дамп обычно будет частичным. Роли и
#   пароли создавай через панель Timeweb, а дамп main БД применяй этим скриптом.
#
#   TODO Sprint 2: добавить --with-globals=<path> для сценария миграции на
#   другого провайдера (где у тебя снова есть superuser).
# =============================================================================
set -euo pipefail

BACKUP_FILE="${1:-}"
if [[ -z "$BACKUP_FILE" ]]; then
    echo "Usage: $0 <path-to-*.sql.gz>" >&2
    exit 1
fi
if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "[restore] FATAL: file not found: $BACKUP_FILE" >&2
    exit 1
fi

PROJECT_DIR="${PROJECT_DIR:-/opt/code9-analytics}"
COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_DIR}/deploy/docker-compose.prod.timeweb.yml}"
PG_IMAGE="${PG_IMAGE:-postgres:18-alpine}"

ENV_FILE="${ENV_FILE:-${PROJECT_DIR}/.env.production}"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_PORT:?POSTGRES_PORT is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"

# --- Safety confirm -------------------------------------------------------
echo "[restore] target: ${POSTGRES_DB} @ ${POSTGRES_HOST}:${POSTGRES_PORT}"
echo "[restore] source: ${BACKUP_FILE}"
echo "[restore] DROP + CREATE будет выполнен через --clean --if-exists в дампе."
echo "[restore] Убедись, что это именно тот кластер, который ты хочешь переписать."
read -r -p "Напечатай 'YES RESTORE' для продолжения: " CONFIRM
if [[ "$CONFIRM" != "YES RESTORE" ]]; then
    echo "[restore] aborted"
    exit 1
fi

# --- Остановка worker / scheduler (если compose-стек запущен) -------------
if [[ -f "$COMPOSE_FILE" ]] && docker compose -f "$COMPOSE_FILE" ps --status=running --services 2>/dev/null | grep -qE '^(worker|scheduler)$'; then
    echo "[restore] stopping worker/scheduler..."
    docker compose -f "$COMPOSE_FILE" stop worker scheduler || true
    RESTART_WORKERS=1
else
    echo "[restore] worker/scheduler не запущены — пропускаем stop"
    RESTART_WORKERS=0
fi

# --- Сам restore ----------------------------------------------------------
echo "[restore] streaming dump → psql..."
gunzip -c "$BACKUP_FILE" \
    | docker run --rm -i \
        --network host \
        -e PGPASSWORD="$POSTGRES_PASSWORD" \
        "$PG_IMAGE" \
        psql \
            --host="$POSTGRES_HOST" \
            --port="$POSTGRES_PORT" \
            --username="$POSTGRES_USER" \
            --dbname="$POSTGRES_DB" \
            --set ON_ERROR_STOP=on

# --- Старт worker / scheduler обратно -------------------------------------
if [[ "$RESTART_WORKERS" == "1" ]]; then
    echo "[restore] restarting worker/scheduler..."
    docker compose -f "$COMPOSE_FILE" start worker scheduler
fi

echo "[restore] done — проверь логи и прогони smoke"
