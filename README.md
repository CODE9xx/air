# Code9 Analytics

SaaS-платформа для подключения amoCRM / Kommo / Bitrix24: CRM-аудит, выгрузка данных, дашборды и AI-аналитика разговоров. Помогает B2B-командам найти узкие места в воронке продаж и повысить конверсию.

**Статус:** MVP Wave 4 — Demo Ready (2026-04-18)

---

## Архитектура

```
┌─────────────┐   HTTP/REST    ┌──────────────────┐
│  Web (3000) │ ◄────────────► │   API (8000)      │
│  Next.js 14 │                │   FastAPI + PY    │
└─────────────┘                └────────┬─────────┘
                                        │  RQ jobs
                               ┌────────▼─────────┐
                               │   Worker (RQ)     │
                               │   Python 3.11     │
                               └────────┬─────────┘
                                        │
              ┌─────────────────────────┼──────────────────┐
              │                         │                  │
    ┌─────────▼────────┐    ┌──────────▼───────┐  ┌──────▼────────┐
    │  Postgres 18      │    │   Redis 7         │  │  packages/    │
    │  main: public     │    │   cache + queues  │  │  crm-connectors│
    │  tenants: crm_*   │    └───────────────────┘  │  ai/          │
    └──────────────────┘                             └──────────────┘
```

**Очереди RQ:** `crm`, `export`, `audit`, `ai`, `retention`, `billing`
**Tenant isolation:** каждое CRM-подключение → отдельная Postgres schema `crm_<provider>_<shortid>`

---

## Quick Start

```bash
cp .env.example .env
make demo
```

Полный стек поднимается, применяются миграции, создаётся admin. Открыть http://localhost:3000

---

## MVP Demo Scenario

1. Открыть http://localhost:3000 — убедиться, что интерфейс на RU
2. Перейти на `/register` → ввести email + пароль → нажать "Зарегистрироваться"
3. В логах api найти `EMAIL ->` строку с кодом подтверждения: `docker compose logs api | grep EMAIL`
4. Перейти на `/verify-email` → ввести 6-значный код → подтвердить email
5. Войти на `/login` → убедиться, что cookie `code9_refresh` установлен
6. Создать workspace (создаётся автоматически при регистрации)
7. Перейти в раздел CRM → нажать "Подключить amoCRM (mock)" → дождаться `status=active`
8. Нажать "Запустить аудит" → дождаться завершения job → открыть отчёт с метриками
9. Открыть Dashboard → посмотреть воронку продаж и активность менеджеров
10. Открыть http://localhost:8000/api/v1/admin/auth/login (admin panel) → войти с `admin@code9.local` / `admin-demo-password` → посмотреть список воркспейсов

---

## Roles & Зоны

Карта владения файлами — [`docs/architecture/FILE_OWNERSHIP.md`](docs/architecture/FILE_OWNERSHIP.md)

| Роль | Зона |
|------|------|
| Lead Architect | `infra/`, `docker-compose.yml`, `docs/`, `Makefile`, `.env.example`, `README.md` |
| Backend Engineer | `apps/api/`, `packages/ai/` |
| DB & Worker Engineer | `apps/worker/`, `scripts/` |
| Frontend Engineer | `apps/web/` |
| CRM Integration | `packages/crm-connectors/` |

---

## Known Gaps (MVP → V1)

Следующие P1-задачи отложены до V1:

1. **Rolling refresh-token** (CR-05) — refresh-токен не ротируется при `/auth/refresh`. Скомпрометированный токен действителен 30 дней.
2. **CSRF-токены** (P1-006) — нет `X-Code9-CSRF` header на mutating endpoints. Частично компенсируется `SameSite=Lax`.
3. **Tenant support-mode endpoints** (CR-07) — `/admin/support-mode/session/:id/tenant/*` не реализованы (AC-11 FAIL).
4. **Реальные внешние интеграции** — amoCRM/Kommo/Bitrix24 OAuth, YooKassa/Stripe, LLM API — все в mock-режиме.
5. **Реальный SMTP** — email-коды выводятся в stdout (DEV_EMAIL_MODE=log). В production нужен настоящий email-провайдер.

---

## Документация

| Документ | Описание |
|----------|----------|
| [`docs/architecture/DECISIONS.md`](docs/architecture/DECISIONS.md) | ADR-лог архитектурных решений |
| [`docs/architecture/CHANGE_REQUESTS.md`](docs/architecture/CHANGE_REQUESTS.md) | CR-журнал (CR-01 ... CR-08) |
| [`docs/api/CONTRACT.md`](docs/api/CONTRACT.md) | API контракт |
| [`docs/security/AUTH.md`](docs/security/AUTH.md) | Аутентификация и авторизация |
| [`docs/db/SCHEMA.md`](docs/db/SCHEMA.md) | Схема БД |
| [`docs/ai/ANONYMIZER_RULES.md`](docs/ai/ANONYMIZER_RULES.md) | Правила анонимизации PII |
| [`docs/qa/DEFECTS.md`](docs/qa/DEFECTS.md) | Открытые дефекты |
| [`docs/demo/RUN_BOOK.md`](docs/demo/RUN_BOOK.md) | Пошаговый runbook для демо |
| [`docs/architecture/WAVE4_REPORT.md`](docs/architecture/WAVE4_REPORT.md) | Отчёт Wave 4 |

---

## Make-команды

```
make up        — поднять стек
make down      — остановить (удаляет volumes)
make logs      — логи api + worker
make migrate   — применить alembic-миграции
make seed      — сидировать admin + demo данные
make test      — запустить pytest
make lint      — ruff проверка
make demo      — полный старт для демо
make fresh     — полный сброс: clean + build + up
make psql      — psql в postgres-контейнере
make redis-cli — redis-cli
```

---

## Лицензия / Owner

TBD — проприетарная лицензия Code9 Analytics.
