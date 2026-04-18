# apps/api — Code9 FastAPI backend

**Owner:** Backend Engineer.
**Wave 1 (сейчас):** только `app/main.py` с `/` и `/health`, `pyproject.toml`.
**Wave 2:** Backend Engineer реализует роутеры, модели и сервисы согласно:

- `docs/api/CONTRACT.md` — контракт endpoints
- `docs/db/SCHEMA.md` — схема БД
- `docs/security/AUTH.md` — авторизация
- `docs/security/OAUTH_TOKENS.md` — шифрование токенов CRM

## Локальный запуск (внутри docker-compose)

```bash
docker compose up api
# API: http://localhost:8000
# Health: http://localhost:8000/health
```

## Локальный запуск (вне docker)

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload --port 8000
```

## Структура (целевая, Wave 2)

```
app/
  main.py                  # FastAPI app + include_router
  core/                    # settings, logging, security-utils, redis, db-session
  auth/                    # register, login, refresh, email-verify
  users/
  workspaces/
  crm/                     # connections, oauth, audit, export
  dashboards/
  billing/
  jobs/                    # enqueue + status
  notifications/
  ai/                      # analysis endpoints
  admin/                   # admin panel endpoints
  db/
    models/
    migrations/            # alembic
tests/
```
