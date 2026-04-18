# Code9 Analytics — dev Makefile
# Все команды предполагают Docker Desktop / OrbStack.

.PHONY: help up down build logs ps restart clean fresh psql redis-cli api-shell worker-shell web-shell migrate seed test lint demo \
        prod-build prod-up prod-down prod-logs prod-ps prod-migrate prod-seed prod-smoke prod-shell-api prod-shell-worker prod-psql prod-config prod-backup prod-restore \
        prod-tw-config prod-tw-build prod-tw-up prod-tw-down prod-tw-logs prod-tw-ps prod-tw-migrate prod-tw-seed prod-tw-smoke prod-tw-backup prod-tw-restore prod-tw-shell-api prod-tw-shell-worker prod-tw-db-extensions prod-tw-db-check prod-tw-psql

PROD_COMPOSE    := docker compose -f deploy/docker-compose.prod.yml --env-file .env.production
PROD_TW_COMPOSE := docker compose -f deploy/docker-compose.prod.timeweb.yml --env-file .env.production

help:
	@echo "Code9 Analytics — команды разработки"
	@echo ""
	@echo "  make up           — поднять весь стек (postgres, redis, api, worker, web)"
	@echo "  make down         — остановить стек (сохраняет volumes)"
	@echo "  make build        — пересобрать все образы"
	@echo "  make logs         — следить за логами api + worker"
	@echo "  make ps           — статус контейнеров"
	@echo "  make restart      — перезапуск всех сервисов"
	@echo "  make clean        — down -v (ВНИМАНИЕ: данные пропадут)"
	@echo "  make fresh        — clean + build + up (полный сброс окружения)"
	@echo "  make migrate      — применить alembic-миграции (main schema)"
	@echo "  make seed         — сидировать admin + demo workspace"
	@echo "  make test         — запустить pytest в контейнере api"
	@echo "  make lint         — ruff check + format check"
	@echo "  make demo         — up + wait + migrate + seed → открыть localhost:3000"
	@echo "  make psql         — открыть psql в контейнере postgres"
	@echo "  make redis-cli    — открыть redis-cli"
	@echo "  make api-shell    — bash в контейнере api"
	@echo "  make worker-shell — bash в контейнере worker"
	@echo "  make web-shell    — sh в контейнере web"
	@echo ""
	@echo "Production (staging / closed pilot) — deploy/docker-compose.prod.yml"
	@echo "  make prod-config       — проверить валидность prod compose (docker compose config)"
	@echo "  make prod-build        — собрать prod-образы (api/worker/web)"
	@echo "  make prod-up           — поднять prod-стек (caddy+web+api+worker+scheduler+postgres+redis)"
	@echo "  make prod-down         — остановить prod-стек (volumes сохраняются)"
	@echo "  make prod-logs         — следить за логами api+worker+caddy"
	@echo "  make prod-ps           — статус prod-контейнеров"
	@echo "  make prod-migrate      — применить alembic миграции в prod-контейнере"
	@echo "  make prod-seed         — admin bootstrap (ОСТОРОЖНО: запускать только один раз)"
	@echo "  make prod-smoke        — curl https://api.\$${DOMAIN}/api/v1/health"
	@echo "  make prod-backup       — запустить deploy/backup/pg_dump.sh"
	@echo "  make prod-shell-api    — bash в prod api"
	@echo "  make prod-shell-worker — bash в prod worker"
	@echo "  make prod-psql         — psql в prod postgres"
	@echo ""
	@echo "Timeweb (VPS + managed Postgres) — deploy/docker-compose.prod.timeweb.yml"
	@echo "  make prod-tw-db-check        — проверить подключение VPS → managed Postgres"
	@echo "  make prod-tw-db-extensions   — создать pgcrypto/uuid-ossp/citext в managed БД (одноразово)"
	@echo "  make prod-tw-config/build/up/down/logs/ps — аналог prod-* для Timeweb-compose"
	@echo "  make prod-tw-migrate/seed/smoke           — миграции / seed admin / smoke /health"
	@echo "  make prod-tw-backup          — pg_dump managed БД через postgres:18-alpine"
	@echo "  make prod-tw-restore BACKUP=<path> — restore managed БД"
	@echo "  make prod-tw-psql            — psql в managed БД (через одноразовый контейнер)"

up:
	docker compose up -d

down:
	docker compose down -v

logs:
	docker compose logs -f api worker

migrate:
	docker compose exec api alembic -c app/db/migrations/alembic.ini --name main upgrade head

seed:
	docker compose exec api python scripts/seed/seed_admin.py
	docker compose exec api python scripts/seed/seed_demo_workspace.py

test:
	docker compose exec api pytest tests/ -q

lint:
	docker compose exec api ruff check .
	docker compose exec api ruff format --check .

demo: up
	@echo "Ожидаем запуск сервисов (10 сек)..."
	sleep 10
	$(MAKE) migrate
	$(MAKE) seed
	@echo ""
	@echo "→ Откройте http://localhost:3000"

build:
	docker compose build

ps:
	docker compose ps

restart:
	docker compose restart

clean:
	docker compose down -v

fresh: clean build up

psql:
	docker compose exec postgres psql -U $${POSTGRES_USER:-code9} -d $${POSTGRES_DB:-code9}

redis-cli:
	docker compose exec redis redis-cli

api-shell:
	docker compose exec api bash

worker-shell:
	docker compose exec worker bash

web-shell:
	docker compose exec web sh

# =============================================================================
# Production targets — deploy/docker-compose.prod.yml
# Перед первым запуском:
#   cp .env.production.template .env.production
#   nano .env.production             # CHANGE_ME → реальные секреты
#   chmod 600 .env.production
# Документация: docs/deploy/SERVER_SETUP.md, docs/deploy/PRODUCTION_CHECKLIST.md
# =============================================================================

prod-config:
	@test -f .env.production || (echo "FATAL: .env.production не найден. Скопируй из .env.production.template" && exit 1)
	$(PROD_COMPOSE) config --quiet && echo "✓ docker-compose.prod.yml валиден"

prod-build:
	@test -f .env.production || (echo "FATAL: .env.production не найден" && exit 1)
	$(PROD_COMPOSE) build

prod-up:
	@test -f .env.production || (echo "FATAL: .env.production не найден" && exit 1)
	$(PROD_COMPOSE) up -d

prod-down:
	$(PROD_COMPOSE) down

prod-logs:
	$(PROD_COMPOSE) logs -f api worker caddy

prod-ps:
	$(PROD_COMPOSE) ps

prod-migrate:
	$(PROD_COMPOSE) exec api alembic -c app/db/migrations/alembic.ini --name main upgrade head

prod-seed:
	@echo "ВНИМАНИЕ: seed admin одноразовый. После первого логина смени пароль в UI."
	$(PROD_COMPOSE) exec api python /app/scripts/seed/seed_admin.py

prod-smoke:
	@DOMAIN="$${PUBLIC_API_URL:-https://api.example.com}"; \
	 echo "→ GET $$DOMAIN/api/v1/health"; \
	 curl -fsS --max-time 10 "$$DOMAIN/api/v1/health" && echo "\n✓ prod-smoke OK" || (echo "\n✗ prod-smoke FAILED" && exit 1)

prod-backup:
	PROJECT_DIR="$(PWD)" \
	  COMPOSE_FILE="$(PWD)/deploy/docker-compose.prod.yml" \
	  ENV_FILE="$(PWD)/.env.production" \
	  bash deploy/backup/pg_dump.sh

prod-restore:
	@echo "Usage: make prod-restore BACKUP=/var/backups/code9/code9_YYYYMMDD_HHMMSSZ.sql.gz"
	@test -n "$(BACKUP)" || (echo "FATAL: передай BACKUP=<path>" && exit 1)
	PROJECT_DIR="$(PWD)" \
	  COMPOSE_FILE="$(PWD)/deploy/docker-compose.prod.yml" \
	  ENV_FILE="$(PWD)/.env.production" \
	  bash deploy/backup/restore.sh "$(BACKUP)"

prod-shell-api:
	$(PROD_COMPOSE) exec api bash

prod-shell-worker:
	$(PROD_COMPOSE) exec worker bash

prod-psql:
	$(PROD_COMPOSE) exec postgres psql -U $${POSTGRES_USER:-code9} -d $${POSTGRES_DB:-code9}

# =============================================================================
# Timeweb production targets — deploy/docker-compose.prod.timeweb.yml
# VPS (web/api/worker/scheduler/caddy/redis) + managed Postgres (внешний).
# Документация: docs/deploy/INSTALL_TIMEWEB.md
# =============================================================================

prod-tw-config:
	@test -f .env.production || (echo "FATAL: .env.production не найден. Скопируй из .env.production.template" && exit 1)
	$(PROD_TW_COMPOSE) config --quiet && echo "✓ docker-compose.prod.timeweb.yml валиден"

prod-tw-build:
	@test -f .env.production || (echo "FATAL: .env.production не найден" && exit 1)
	$(PROD_TW_COMPOSE) build

prod-tw-up:
	@test -f .env.production || (echo "FATAL: .env.production не найден" && exit 1)
	$(PROD_TW_COMPOSE) up -d

prod-tw-down:
	$(PROD_TW_COMPOSE) down

prod-tw-logs:
	$(PROD_TW_COMPOSE) logs -f api worker caddy

prod-tw-ps:
	$(PROD_TW_COMPOSE) ps

# Проверка связности VPS → managed Postgres (DNS + TCP + auth).
# Выполняется одноразовым контейнером postgres:18-alpine (psql установлен) с --network host.
prod-tw-db-check:
	@set -a; . ./.env.production; set +a; \
	 : "$${POSTGRES_HOST:?POSTGRES_HOST не задан в .env.production}"; \
	 : "$${POSTGRES_PORT:?POSTGRES_PORT не задан}"; \
	 : "$${POSTGRES_USER:?POSTGRES_USER не задан}"; \
	 : "$${POSTGRES_PASSWORD:?POSTGRES_PASSWORD не задан}"; \
	 : "$${POSTGRES_DB:?POSTGRES_DB не задан}"; \
	 echo "→ проверка $${POSTGRES_HOST}:$${POSTGRES_PORT} db=$${POSTGRES_DB} user=$${POSTGRES_USER}"; \
	 docker run --rm --network host -e PGPASSWORD="$${POSTGRES_PASSWORD}" postgres:18-alpine \
	   psql -h "$${POSTGRES_HOST}" -p "$${POSTGRES_PORT}" -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}" -c "select version();" \
	 && echo "✓ managed Postgres доступен и авторизация прошла"

# Одноразово: создать расширения pgcrypto / uuid-ossp / citext в managed БД.
# На Timeweb по умолчанию разрешены (дефолтный public schema). Если нет прав — выдаст ошибку.
prod-tw-db-extensions:
	@set -a; . ./.env.production; set +a; \
	 : "$${POSTGRES_HOST:?POSTGRES_HOST не задан}"; \
	 echo "→ CREATE EXTENSION pgcrypto, uuid-ossp, citext в $${POSTGRES_DB}"; \
	 docker run --rm --network host -e PGPASSWORD="$${POSTGRES_PASSWORD}" postgres:18-alpine \
	   psql -h "$${POSTGRES_HOST}" -p "$${POSTGRES_PORT}" -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}" \
	        --set ON_ERROR_STOP=on \
	        -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" \
	        -c "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";" \
	        -c "CREATE EXTENSION IF NOT EXISTS citext;" \
	 && echo "✓ extensions установлены"

prod-tw-migrate:
	$(PROD_TW_COMPOSE) exec api alembic -c app/db/migrations/alembic.ini --name main upgrade head

prod-tw-seed:
	@echo "ВНИМАНИЕ: seed admin одноразовый. После первого логина смени пароль в UI."
	$(PROD_TW_COMPOSE) exec api python /app/scripts/seed/seed_admin.py

prod-tw-smoke:
	@DOMAIN="$${PUBLIC_API_URL:-https://api.example.com}"; \
	 echo "→ GET $$DOMAIN/api/v1/health"; \
	 curl -fsS --max-time 10 "$$DOMAIN/api/v1/health" && echo "\n✓ prod-tw-smoke OK" || (echo "\n✗ prod-tw-smoke FAILED" && exit 1)

prod-tw-backup:
	PROJECT_DIR="$(PWD)" \
	  COMPOSE_FILE="$(PWD)/deploy/docker-compose.prod.timeweb.yml" \
	  ENV_FILE="$(PWD)/.env.production" \
	  bash deploy/backup/pg_dump_managed.sh

prod-tw-restore:
	@echo "Usage: make prod-tw-restore BACKUP=/var/backups/code9/code9_YYYYMMDD_HHMMSSZ.sql.gz"
	@test -n "$(BACKUP)" || (echo "FATAL: передай BACKUP=<path>" && exit 1)
	PROJECT_DIR="$(PWD)" \
	  COMPOSE_FILE="$(PWD)/deploy/docker-compose.prod.timeweb.yml" \
	  ENV_FILE="$(PWD)/.env.production" \
	  bash deploy/backup/restore_managed.sh "$(BACKUP)"

prod-tw-shell-api:
	$(PROD_TW_COMPOSE) exec api bash

prod-tw-shell-worker:
	$(PROD_TW_COMPOSE) exec worker bash

# psql в managed БД (через одноразовый контейнер с клиентом). Используй для ad-hoc
# проверок схемы / SELECT'ов. Для миграций — prod-tw-migrate.
prod-tw-psql:
	@set -a; . ./.env.production; set +a; \
	 docker run --rm -it --network host -e PGPASSWORD="$${POSTGRES_PASSWORD}" postgres:18-alpine \
	   psql -h "$${POSTGRES_HOST}" -p "$${POSTGRES_PORT}" -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}"
