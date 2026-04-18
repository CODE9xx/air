# scripts/seed

Скрипты сидеров для локальной разработки и демо.

**Owner:** DB & Worker Engineer.

## Скрипты (Wave 2)

### `seed_admin.py`

Создаёт (или обновляет) bootstrap-админа по env
`ADMIN_BOOTSTRAP_EMAIL` / `ADMIN_BOOTSTRAP_PASSWORD`.

- Идемпотентно.
- Хеш — argon2id с теми же параметрами, что и в `apps/api/app/core/security.py`.
- Пароль в логи НЕ пишется.

```bash
# через api-контейнер (в нём уже есть argon2 + sqlalchemy)
docker compose exec api python /app/scripts/seed/seed_admin.py
# локально (из корня репозитория)
ADMIN_BOOTSTRAP_PASSWORD='your-secret' python -m scripts.seed.seed_admin
```

### `seed_demo_workspace.py`

Создаёт демо-пользователя + workspace + pending `crm_connections` row.

```bash
docker compose exec api python /app/scripts/seed/seed_demo_workspace.py
```

## Зависимости

- `argon2-cffi` — уже в `apps/api/pyproject.toml` и `apps/worker/pyproject.toml`.
- `sqlalchemy` + `psycopg2-binary` — те же.

## Порядок запуска

```bash
# 1. Применить main-миграции
docker compose exec api alembic \
    -c /app/app/db/migrations/alembic.ini --name main upgrade head

# 2. Создать bootstrap-админа
docker compose exec api python /app/scripts/seed/seed_admin.py

# 3. (опц.) Создать demo workspace
docker compose exec api python /app/scripts/seed/seed_demo_workspace.py
```
