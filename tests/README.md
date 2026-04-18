# Tests — Code9 Analytics

## Структура

```
tests/
  conftest.py             — общие фикстуры (httpx client, db session, redis flush)
  api/
    test_auth.py          — register, verify, login, refresh, logout, password reset
    test_workspace.py     — workspace, CRM connections (auth checks), delete flow
    test_admin.py         — admin login, support mode, audit logs, rate limit
  security/
    test_token_leak.py    — caplog/capsys проверка: нет raw-токенов в логах
    test_anonymizer.py    — golden corpus PII (email, phone RU/EN, ИНН, card, IP, passport)
  e2e/
    test_connect_sync_audit.py — mock connection → sync → audit → dashboard (integration)
```

## Как запускать

### В Docker (рекомендуемый способ):

```bash
# Предварительно поднять все контейнеры:
docker compose up -d

# Применить миграции:
docker compose exec api alembic -c apps/api/app/db/migrations/alembic.ini upgrade head

# Запустить seed:
docker compose exec api python scripts/seed/seed_admin.py

# Запустить все тесты:
docker compose exec api pytest -q --asyncio-mode=auto tests/

# Только unit-тесты (без интеграции):
docker compose exec api pytest -q --asyncio-mode=auto tests/ -m "not integration"

# Только security-тесты:
docker compose exec api pytest -q --asyncio-mode=auto tests/security/

# С verbose выводом:
docker compose exec api pytest -v --asyncio-mode=auto tests/
```

### Локально (если установлены зависимости):

```bash
# Создать тестовую БД:
createdb code9_test

# Применить миграции к тестовой БД:
DATABASE_URL=postgresql+asyncpg://code9:code9@localhost:5432/code9_test \
  alembic -c apps/api/app/db/migrations/alembic.ini upgrade head

# Запустить тесты:
cd /path/to/CODE9_ANALYTICS
pytest -q --asyncio-mode=auto tests/ \
  -e DATABASE_URL=postgresql+asyncpg://code9:code9@localhost:5432/code9_test \
  -e REDIS_URL=redis://localhost:6379/1
```

## Переменные окружения для тестов

| Переменная | Значение по умолчанию (тесты) |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://code9:code9@localhost:5432/code9_test` |
| `REDIS_URL` | `redis://localhost:6379/1` |
| `JWT_SECRET` | `test-jwt-secret-32chars-long-ok` |
| `ADMIN_JWT_SECRET` | `test-admin-jwt-secret-32chars-long` |
| `FERNET_KEY` | `V2fZ7eYm_Qc_f0p-Jb5HcH8XxJz0Aq7W1GH8wKmYP_M=` |
| `APP_ENV` | `test` |
| `MOCK_CRM_MODE` | `true` |

## Маркеры pytest

- `@pytest.mark.integration` — требует работающего Redis + PostgreSQL + Worker
- Без маркера — unit/smoke тесты (только ASGI, не требуют работающей БД)

## Известные ограничения

1. `test_anonymizer.py` — все тесты `pytest.skip` пока `packages/ai/anonymizer.py` не создан (P0-001)
2. E2E-тесты требуют верифицированного email, что без прямого DB-доступа невозможно в unit-среде
3. `test_token_leak.py::test_register_no_token_leak_in_logs` работает полностью в unit-среде
