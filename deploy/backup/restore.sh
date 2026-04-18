#!/usr/bin/env bash
# =============================================================================
# Code9 Analytics — PostgreSQL restore script
#
# ОСТОРОЖНО: скрипт DROP и пересоздаёт таблицы в целевой БД.
# Используй ТОЛЬКО для restore drill на staging или при реальном инциденте.
#
# Usage:
#   ./deploy/backup/restore.sh /var/backups/code9/code9_20260418_030000Z.sql.gz
#
# SCOPE (Gate A / Sprint 0):
#   Этот скрипт восстанавливает ТОЛЬКО main DB dump (code9_<stamp>.sql.gz).
#   Он НЕ применяет globals-дамп (code9_globals_<stamp>.sql.gz) — на существующем
#   кластере роль POSTGRES_USER уже есть и main-dump не использует --create/--globals,
#   поэтому для restore drill и in-place recovery этого достаточно.
#
# TODO Sprint 2 / backup hardening:
#   Полный disaster recovery на ЧИСТОЙ VPS должен:
#     1. Поднять чистый postgres-контейнер.
#     2. Восстановить globals-дамп через `psql -U postgres` (роли, tablespaces).
#     3. Только ПОТОМ восстановить main dump.
#   Пока это делается вручную — см. docs/deploy/BACKUP_RESTORE.md §8.
#   План: добавить параметр --with-globals=<path>, который выполняет шаги 1-3
#   последовательно и проверяет соответствие версий дампов.
#
# Процедура restore drill (делай минимум раз в 2 недели до pilot):
#   1. Запустить свежий prod compose на staging-окружении.
#   2. Прогнать restore.sh на последний дамп.
#   3. make prod-smoke + ручная проверка dashboard / admin.
#   4. Зафиксировать время RTO в docs/deploy/BACKUP_RESTORE.md.
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
COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_DIR}/deploy/docker-compose.prod.yml}"
SERVICE="${SERVICE:-postgres}"

ENV_FILE="${ENV_FILE:-${PROJECT_DIR}/.env.production}"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"

# --- Safety confirm -------------------------------------------------------
echo "[restore] target: ${POSTGRES_DB} on service '${SERVICE}'"
echo "[restore] source: ${BACKUP_FILE}"
echo "[restore] DROP + CREATE будет выполнен через --clean --if-exists в дампе."
read -r -p "Напечатай 'YES RESTORE' для продолжения: " CONFIRM
if [[ "$CONFIRM" != "YES RESTORE" ]]; then
    echo "[restore] aborted"
    exit 1
fi

echo "[restore] stopping worker/scheduler (чтобы jobs не писали во время restore)..."
docker compose -f "$COMPOSE_FILE" stop worker scheduler || true

echo "[restore] streaming dump → psql..."
gunzip -c "$BACKUP_FILE" \
    | docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" \
        psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" \
             --set ON_ERROR_STOP=on

echo "[restore] restarting worker/scheduler..."
docker compose -f "$COMPOSE_FILE" start worker scheduler

echo "[restore] done — проверь логи и прогони smoke"
