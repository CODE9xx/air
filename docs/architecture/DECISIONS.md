# Architecture Decision Record (ADR) — Code9 Analytics

Формат: каждое решение — короткий блок. Статусы: `Accepted`, `Proposed`, `Superseded`.

---

## ADR-001. Backend на FastAPI + Python 3.11
**Status:** Accepted (Wave 1, Lead Architect).
**Контекст:** нужен async backend с OpenAPI, pydantic, миграциями, воркерами.
**Решение:** FastAPI 0.111+, Python 3.11-slim в Docker, uvicorn standalone.
**Альтернативы:** NestJS (Node), Django REST, Go/Echo.
**Последствия:** одна экосистема Python для api+worker, легко шарить модели.

---

## ADR-002. Multi-tenant через отдельные Postgres schemas
**Status:** Accepted.
**Контекст:** клиентские данные CRM должны быть изолированы; в одной БД не должны случайно смешаться.
**Решение:** `public` — main app (users, workspaces, crm_connections, billing…). Каждое активное подключение получает свою schema `crm_<provider>_<shortid>` (например `crm_amo_a7f3c8e2`). Создаётся при переходе `crm_connections.status -> active`, удаляется `DROP SCHEMA ... CASCADE` при финальном удалении.
**Альтернативы:** отдельная БД на tenant (дорого), row-level isolation `workspace_id` в каждой таблице (легко ошибиться в запросе).
**Последствия:** нужно аккуратно применять миграции ко всем tenant-schemas; `search_path` управляется SA-сессией.

---

## ADR-003. Redis + RQ для фоновых задач
**Status:** Accepted.
**Контекст:** CRM-sync, экспорт, AI, retention — всё долгие IO-задачи, не должны блокировать HTTP.
**Решение:** RQ 1.16 на Redis 7. Очереди: `crm`, `export`, `audit`, `ai`, `retention`, `billing`.
**Альтернативы:** Celery (overkill для MVP), Dramatiq, Arq.
**Последствия:** простое развёртывание, минимум кода; если понадобится scheduler — добавим `rq-scheduler`.

---

## ADR-004. Frontend на Next.js 14 App Router + next-intl
**Status:** Accepted.
**Контекст:** нужна i18n RU+EN, SSR для маркетинговых страниц, hydration для дашбордов.
**Решение:** Next.js 14 App Router + `next-intl` (middleware + `useTranslations`).
**Альтернативы:** Remix (меньше экосистемы), Vite SPA (нет SSR), `react-i18next` (больше кода в App Router).
**Последствия:** единый TS-проект, Server Actions для простых мутаций.

---

## ADR-005. Mock-first режим (MOCK_CRM_MODE)
**Status:** Accepted.
**Контекст:** реальные amoCRM/Kommo OAuth доступны только после ревью партнёра; YooKassa/Stripe требуют бизнес-верификации; LLM API — денег.
**Решение:** флаг `MOCK_CRM_MODE=true` включает фикстуры для всех внешних HTTP (CRM, платежи, LLM). В MVP всегда `true`.
**Альтернативы:** использовать sandbox провайдеров (не всегда доступны).
**Последствия:** полное прохождение end-to-end сценария без интернета; фикстуры живут в `packages/crm-connectors/fixtures/`.

---

## ADR-006. Шифрование OAuth-токенов Fernet
**Status:** Accepted.
**Контекст:** access/refresh токены amoCRM — боевые секреты клиентов. Нельзя хранить в открытом виде.
**Решение:** Fernet (AES-128-CBC + HMAC) с ключом из `FERNET_KEY` env. Поля `access_token_encrypted`, `refresh_token_encrypted` в `crm_connections`. Никогда не логируем, никогда не возвращаем в API.
**Альтернативы:** pgcrypto column-level (сложнее ротация ключей), KMS (overkill MVP).
**Последствия:** ротация ключей — V1 (нужно держать два ключа при ротации). Refresh — только в worker-job, не в request cycle.

---

## ADR-007. Destructive actions через email-код
**Status:** Accepted.
**Контекст:** удаление CRM-подключения, сброс пароля, отзыв доступа — нельзя разрешать одним кликом.
**Решение:** 6-значный numeric код, argon2-hash в БД, TTL 10-15 min, ≤5 попыток. Purpose enum (`email_verify`, `password_reset`, `connection_delete`).
**Альтернативы:** TOTP (сложнее UX), magic link (уязвим к fishing).
**Последствия:** DEV_EMAIL_MODE=log в dev — код виден в логах api.

---

## ADR-008. Аудит-лог всех админ-действий в той же транзакции
**Status:** Accepted.
**Контекст:** внутренние злоупотребления — главный риск в SaaS. Нужна железная трассировка.
**Решение:** каждое действие админа и запись в `admin_audit_logs` — одна транзакция. Если лог не записался — действие откатывается.
**Альтернативы:** async-лог (риск потери).
**Последствия:** чуть медленнее; но быстрее, чем объяснять клиенту, кто и зачем трогал его данные.

---

## ADR-009. Retention 90 дней после расторжения
**Status:** Accepted.
**Контекст:** нужно удалять данные отключённых клиентов автоматически, с уведомлениями.
**Решение:** jobs `retention_warning` (60/75/85 дней), `retention_read_only` (30), `retention_delete` (90). Детали — в `security/RETENTION_POLICY.md`.
**Последствия:** одна cron-like-задача в воркере (rq-scheduler в Wave 2).

---

## ADR-010. Research consent + анонимизация для AI
**Status:** Accepted.
**Контекст:** хотим улучшать модели/бенчмарки на реальных паттернах, но GDPR/152-ФЗ требуют явного согласия и анонимизации.
**Решение:** `ai_research_consent` с `status in (not_asked, accepted, revoked)`. Анонимайзер блэк/вайт-листов (`ai/ANONYMIZER_RULES.md`). Минимальный `sample_size=10`; `privacy_risk=high` → `should_store=false`.
**Альтернативы:** хранить всё сырым (неприемлемо), не хранить ничего (теряем возможность улучшать продукт).
**Последствия:** все AI-артефакты проходят через `anonymize` job; сохраняются только паттерны.

---

## ADR-011. Fail-fast валидация production-секретов при старте
**Status:** Accepted (Wave 4, Lead Architect, 2026-04-18).
**Контекст:** JWT_SECRET, ADMIN_JWT_SECRET, FERNET_KEY имеют публичные дефолты в settings.py (обнаружено QA Wave 3). При деплое без перекрытия ENV — токены будут подписываться/шифроваться публичным ключом.
**Решение:** `@model_validator(mode="after")` в `Settings` — если APP_ENV=production и любой из секретов равен дефолтному значению, приложение падает при старте с `ValueError`.
**Альтернативы:** runtime-проверка при первом запросе (слишком поздно); убрать дефолты (сломает dev).
**Последствия:** в production нельзя запустить без явно заданных секретов. Dev не затронут.

---

## ADR-012. Tenant-schema regex с обязательным prefix crm_
**Status:** Accepted (Wave 4, Lead Architect, 2026-04-18).
**Контекст:** regex `^[a-z_][a-z0-9_]{0,62}$` допускал зарезервированные имена PostgreSQL. `DROP SCHEMA public CASCADE` → катастрофа.
**Решение:** Заменить на `^crm_[a-z0-9][a-z0-9_]{1,59}$` в обоих местах валидации (worker/lib/tenant.py и scripts/migrations/apply_tenant_template.py).
**Альтернативы:** Runtime check в DDL-функции (дублирование); allowlist имён (хрупко).
**Последствия:** Все существующие tenant-схемы начинаются с crm_ по генератору — обратно совместимо.

---

## ADR-013. MVP demo с mock-first режимом для всех внешних зависимостей
**Status:** Accepted (Wave 4, Lead Architect, 2026-04-18).
**Контекст:** Реальные amoCRM/Kommo OAuth, YooKassa/Stripe, LLM API требуют бизнес-верификации, договоров и денег. MVP-demo должен работать без интернета.
**Решение:** MOCK_CRM_MODE=true + EMAIL_BACKEND=console. Все внешние вызовы заменены фикстурами. Дефолт в .env.example — mock.
**Последствия:** полное сквозное прохождение сценария без внешних зависимостей; чёткая граница "mock → real" через env-флаг.
