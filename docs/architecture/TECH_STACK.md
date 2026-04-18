# Tech Stack — Code9 Analytics

## Backend (apps/api)

| Компонент | Выбор | Почему |
|---|---|---|
| Язык | Python 3.11 | async/await mature, типы, богатая экосистема для data/ML. |
| Framework | FastAPI 0.111+ | async, pydantic v2, OpenAPI out-of-the-box, ADR-001. |
| ORM | SQLAlchemy 2.0 (async) | поддержка `asyncpg`, mature. |
| Migrations | Alembic | стандарт для SA, будет использоваться и для tenant-schema. |
| Driver | asyncpg (rт) + psycopg2 (alembic) | asyncpg — быстрый; psycopg2 — для alembic sync. |
| Auth | `python-jose` + `argon2-cffi` | JWT HS256 + argon2id. |
| Crypto | `cryptography` (Fernet) | шифрование токенов CRM at rest. |
| HTTP client | `httpx` | async, используется в CRM-коннекторах. |
| Jobs | RQ 1.16+ | простой, Redis-based, достаточен для MVP (vs Celery). |
| Logging | `structlog` | structured JSON-логи. |

## Frontend (apps/web)

| Компонент | Выбор | Почему |
|---|---|---|
| Framework | Next.js 14 App Router | RSC, routing, middleware для i18n. |
| Язык | TypeScript 5.5 | strict mode. |
| i18n | `next-intl` | ADR-004, server+client i18n в App Router. |
| Styling | Tailwind CSS 3.4 | быстрая разработка, design-system позже. |
| Data fetching | Fetch + React Server Actions | без лишнего Redux/TanStack в MVP. |

## Storage

| Компонент | Выбор | Почему |
|---|---|---|
| БД | Postgres 18 alpine | ADR-002, schema-per-tenant. |
| Cache + Queue | Redis 7 alpine | RQ backend + rate-limit store + short-lived cache. |
| Файлы экспорта | локальный volume в MVP, S3-compatible — в V1 | простота. |
| Аудио | **НЕ храним**. При AI-анализе — эфемерно в памяти/tmpfs. |

## Worker (apps/worker)

- RQ 1.16, 6 очередей (см. `apps/worker/README.md`).
- Graceful shutdown по SIGTERM.
- Подключается к той же Postgres и Redis, что и API.

## Infra

| Компонент | Выбор |
|---|---|
| Оркестрация в dev | docker compose v2 |
| Оркестрация в prod | TBD (V1 — предположительно Fly.io / Render / DigitalOcean App Platform) |
| CI | GitHub Actions (настраивается в V1) |
| Секреты | `.env` в dev, переменные окружения платформы в prod |

## Версии пиннятся

- Python: 3.11 slim в Docker, верхняя граница libs зафиксирована в `pyproject.toml`.
- Node: 20-alpine в Docker, package.json зафиксирован с `^` диапазонами.

## Принципы

- **Прагматизм > моды.** Простой стек, широко известный, быстро нанимаемый.
- **Async везде, где IO.** Worker тоже может async внутри job'а.
- **Один язык на бэке.** Python везде, никаких Node-микросервисов в MVP.
- **Явные зависимости между контейнерами.** `depends_on` с `condition: service_healthy`.
