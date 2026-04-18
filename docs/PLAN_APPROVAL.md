# Plan Approval — Code9 Analytics (Wave 1)

> **STATUS: APPROVED** — owner подтвердил все 8 блоков 2026-04-18.
> Решения переносятся в `docs/architecture/DECISIONS.md` как ADR. Wave 2 разрешена.

Ниже — ключевые решения, принятые Lead Architect, требующие явного одобрения владельца проекта перед стартом Wave 2.

Формат: у каждого блока — решение, альтернативы, последствия, чек-листы `YES/NO/ADJUST`.
Отметка нужна ровно одна на блок. После approval — переносим в `docs/architecture/DECISIONS.md`.

---

## AUTH — Пароли и токены

**Решение:** argon2id (par=2, mem=64MB, iter=3) + JWT HS256 access 15 min + opaque refresh 30d в `user_sessions` (httpOnly secure cookie).

**Альтернативы:**
- bcrypt + JWT-only (без refresh в БД) — меньше защиты, невозможно принудительно revoke.
- Session-cookie без JWT — привязка к одному API-origin, сложнее для мобилки.

**Последствия:**
- Добавляется таблица `user_sessions` (и зеркально `admin_sessions` для админов).
- Смена пароля → массовый revoke всех refresh user'а.
- Rate-limit на login через Redis.

**Нужен approval по:** [x] YES [ ] NO [ ] ADJUST  _— approved 2026-04-18_

---

## DB_SCHEMA — Multi-tenant через Postgres schemas

**Решение:** main в `public`, отдельная schema `crm_<provider>_<8-char-lowercase-shortid>` на каждое активное CRM-подключение. Создаётся при `status=active`, дропается при `status=deleted`.

**Альтернативы:**
- Отдельная БД на tenant — дорого в операциях и инфре.
- Row-level `workspace_id` во всех таблицах — легко сделать SELECT без фильтра и смешать данные клиентов.

**Последствия:**
- Два alembic environment'а (main + tenant template).
- Нужен CI-скрипт `apply_tenant_template.py` при новых миграциях.
- `search_path` управляется сессией SA.

**Нужен approval по:** [x] YES [ ] NO [ ] ADJUST  _— approved 2026-04-18_

---

## OAUTH_TOKENS — Хранение токенов CRM

**Решение:** Fernet (AES-128-CBC + HMAC) с ключом из env `FERNET_KEY`. Поля BYTEA в `crm_connections`. Расшифровка только в worker-job'ах. Никогда не в API-ответах и логах. Ротация ключей — V1.

**Альтернативы:**
- pgcrypto column-level — сложнее ротация.
- AWS KMS / Vault — overkill для MVP.

**Последствия:**
- Refresh делает только воркер.
- Нужен log-masker (`Bearer ***`).
- При `invalid_grant` → status=`lost_token`, новые платные jobs не стартуют.

**Нужен approval по:** [x] YES [ ] NO [ ] ADJUST  _— approved 2026-04-18_

---

## DELETION_FLOW — Удаление CRM-подключения

**Решение:** двухшаговый flow через email-код. `deletion_requests` row (TTL 10 min, ≤5 попыток). Подтверждение → job `delete_connection_data` → `DROP SCHEMA ... CASCADE`. После `status=deleted` реактивация запрещена; `billing_ledger` и `admin_audit_logs` сохраняются.

**Альтернативы:**
- «Мягкое» удаление с read-only 30 дней — добавляет сложности и стоит хранилища.
- Удаление по одной кнопке без кода — неприемлемо (catastrophic user error risk).

**Последствия:**
- email-пайплайн обязательно работает (в dev — в лог).
- Job должен быть идемпотентен (повторный запуск не падает).

**Нужен approval по:** [x] YES [ ] NO [ ] ADJUST  _— approved 2026-04-18_

---

## ADMIN_SUPPORT_MODE — Доступ админа к tenant-данным

**Решение:** отдельная таблица `admin_users` + `ADMIN_JWT_SECRET` + scope=`admin`. Нет прямого read-доступа к tenant. Для отладки — Support Mode: start с обязательным `reason`, TTL 60 мин, каждый tenant-запрос в `admin_audit_logs`. `admin_audit_logs` пишется в той же транзакции, что и действие.

**Альтернативы:**
- Единая таблица `users` с флагом `is_admin` — смешение ролей, больше риска.
- Нет админки вообще — невозможно поддерживать клиентов.

**Последствия:**
- Нужна таблица `admin_support_sessions` (добавит DW в миграциях).
- Endpoint'ы `/admin/support-mode/*` обязательно с audit-middleware.

**Нужен approval по:** [x] YES [ ] NO [ ] ADJUST  _— approved 2026-04-18_

---

## AI_RESEARCH_DATASET — Research consent + анонимизация

**Решение:** `ai_research_consent` workspace-scoped (`not_asked`/`accepted`/`revoked`). Анонимайзер с блэк/вайт-листом (см. `ai/ANONYMIZER_RULES.md`). Минимальный `sample_size=10`. `privacy_risk=high` → `should_store=false`. Паттерны агрегируются в `ai_research_patterns` (без workspace/user FK).

**Альтернативы:**
- Хранить всё raw — юридически неприемлемо (GDPR/152-ФЗ).
- Не хранить ничего — теряем возможность улучшать продукт и давать индустриальные бенчмарки.

**Последствия:**
- Анонимайзер — обязательный шаг перед LLM-вызовом и сохранением.
- Отзыв consent не удаляет уже сохранённые паттерны (они полностью анонимны).

**Нужен approval по:** [x] YES [ ] NO [ ] ADJUST  _— approved 2026-04-18_

---

## BILLING_MOCK — Платежи в MVP

**Решение:** в MVP все платёжные провайдеры (YooKassa RU, Stripe EN) работают в mock-режиме. `POST /workspaces/:wsid/billing/deposits` в mock сразу пишет `billing_ledger.kind='deposit'`. Webhook'и принимают mock-payload. Реальные интеграции — V1.

**Альтернативы:**
- Сразу реальный YooKassa — требует бизнес-верификации ИП/ООО + подписанного договора.
- Только один провайдер — сузит рынок в EN-аудитории.

**Последствия:**
- Нужна чёткая mock-логика, чтобы проверять edge-cases (неуспешная оплата, повторный webhook).
- Перед переходом на prod — отдельный тест-план с реальной sandbox-суммой в V1.

**Нужен approval по:** [x] YES [ ] NO [ ] ADJUST  _— approved 2026-04-18_

---

## MULTI_TENANT_SCHEMAS — Именование и lifecycle

**Решение:** `crm_<provider>_<8-char-lowercase-shortid>`, где provider ∈ `amo|kommo|bx24`, shortid = `substr(md5(random()), 1, 8)`. Создание в job `bootstrap_tenant_schema` при переходе `status=active`. Удаление `DROP SCHEMA ... CASCADE` в job `delete_connection_data` или `retention_delete`. Имя хранится в `crm_connections.tenant_schema`.

**Альтернативы:**
- Имя схемы = UUID — длинно, неудобно в psql.
- Имя схемы = slug workspace — коллизии, сложно менять, утечка имени бизнеса в DDL.

**Последствия:**
- Ограничение длины имени schema ≤ 63 символов (Postgres). Наш формат укладывается.
- DDL через `format('CREATE SCHEMA %I', ident)` — защита от SQL injection.

**Нужен approval по:** [x] YES [ ] NO [ ] ADJUST  _— approved 2026-04-18_

---

## Общая инструкция владельцу

1. Пройдись по блокам, отметь YES/NO/ADJUST.
2. Для ADJUST — оставь комментарий в конце блока.
3. После прохода — оркестратор запускает Wave 2 с агентами BE/FE/DW/CRM/QA.

> Замечания по стеку/UX/бизнес-модели, которые здесь не покрыты, — пиши в `docs/architecture/DECISIONS.md` как новый ADR-blockер.
