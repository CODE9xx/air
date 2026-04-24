# Defects Report — Code9 Analytics Wave 2 → Wave 3 QA

**Дата:** 2026-04-18  
**Ревьюер:** QA/Security Engineer

---

## P1-001: Worker log_mask — отсутствуют FERNET_KEY и jwt_secret в SENSITIVE_KEYS

- **Файл:** `apps/worker/worker/lib/log_mask.py:13-25`
- **Описание:** `SENSITIVE_KEYS` в worker-маскировщике не включает `fernet_key` и `jwt_secret`. При случайном логировании этих значений в kwargs — они попадут в stdout без маскировки. API-версия `core/log_mask.py` покрывает оба ключа, но worker использует собственный модуль.
- **Статус:** OPEN
- **Assignee:** DW

---

## P1-002: Refresh token не ротируется при `/auth/refresh` (нет rolling refresh)

- **Файл:** `apps/api/app/auth/router.py:261-308`
- **Описание:** Документ `docs/security/AUTH.md §3` описывает "rolling refresh" (каждый вызов `/auth/refresh` должен выдавать новый refresh-токен и инвалидировать старый). Реализация выдаёт новый access-токен, но cookie и хеш в БД не ротируются. Если refresh-токен будет скомпрометирован, атакующий может использовать его все 30 дней.
- **Статус:** OPEN
- **Assignee:** BE

---

## P1-003: Захардкоженный дефолтный FERNET_KEY в settings.py

- **Файл:** `apps/api/app/core/settings.py:51-52`
- **Описание:** `fernet_key` имеет публичный дефолт `"V2fZ7eYm_Qc_f0p-Jb5HcH8XxJz0Aq7W1GH8wKmYP_M="`. Если разработчик не установит `FERNET_KEY` в `.env` — dev-данные зашифруются этим известным ключом. Любой читающий репозиторий может расшифровать OAuth-токены. Дефолт должен быть пустым с fail-fast при старте.
- **Статус:** OPEN
- **Assignee:** BE + LEAD

---

## P1-004: Regex валидации tenant-схемы не требует prefix `crm_`

- **Файл:** `scripts/migrations/apply_tenant_template.py:22`, `apps/worker/worker/lib/tenant.py:48`
- **Описание:** `_SCHEMA_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")` допускает имена `public`, `information_schema`, `pg_catalog` и т.д. Если через баг или прямую запись в БД `tenant_schema` окажется `public`, вызов `DROP SCHEMA public CASCADE` уничтожит основную схему. Необходимо заменить на `^crm_[a-z0-9_]+$`.
- **Статус:** OPEN
- **Assignee:** DW

---

## P1-005: Tenant-эндпоинты support mode не реализованы

- **Файл:** `apps/api/app/admin/router.py` — отсутствуют роуты
- **Описание:** `docs/security/ADMIN_SUPPORT_MODE.md §Доступ к tenant-данным` описывает эндпоинты `/admin/support-mode/session/:id/tenant/*` с проверкой сессии и audit-логированием каждого запроса. В `admin/router.py` эти роуты полностью отсутствуют. Support-mode можно открыть, но получить tenant-данные через него невозможно.
- **Статус:** OPEN
- **Assignee:** BE

---

## P1-006: Нет CSRF-защиты на mutating endpoints

- **Файл:** `apps/api/app/main.py` (middleware)
- **Описание:** `docs/security/AUTH.md §8` упоминает `X-Code9-CSRF` header как опциональный V1, однако для MVP-demo это приемлемо. Реальная защита — только через `SameSite=Lax` cookie. Для production необходим либо CSRF-токен (Double Submit Cookie), либо переход на `SameSite=Strict`. Помечено как P1 так как требует архитектурного решения до prod.
- **Статус:** OPEN — решение архитектурное
- **Assignee:** BE + LEAD

---

## P2-001: Admin logout не revoke refresh-сессию

- **Файл:** `apps/api/app/admin/router.py:112-116`
- **Описание:** `POST /admin/auth/logout` просто возвращает 204 без revoke admin_session. Таблица `admin_sessions` существует, но logout ею не управляет.
- **Статус:** OPEN
- **Assignee:** BE

---

## P2-002: Нет Redis rate-limit на `/crm/connections/:id/delete/confirm`

- **Файл:** `apps/api/app/crm/router.py:303-374`
- **Описание:** `docs/security/AUTH.md §5` указывает `deletion-confirm 5/10min` как отдельный Redis rate-limit. Реализована защита через `max_attempts` в БД (5 попыток), но без IP-based Redis rate-limit — атакующий с разными connection_id может использовать неограниченное число попыток.
- **Статус:** OPEN
- **Assignee:** BE

---

## P2-003: Tumbling window вместо sliding window в rate limiter

- **Файл:** `apps/api/app/core/rate_limit.py:16-30`
- **Описание:** Реализован tumbling window (`bucket = int(time.time() // window_seconds)`), тогда как `docs/security/AUTH.md §5` упоминает "sliding window". Атакующий может сделать 2×limit запросов на границе каждой минуты.
- **Статус:** OPEN — minor
- **Assignee:** BE

---

## P2-004: Email код пишется в stdout plaintext при DEV_EMAIL_MODE=log

- **Файл:** `apps/api/app/core/email.py:15-17`
- **Описание:** `_emit()` делает `print(msg)` где `msg` содержит код подтверждения. Это задокументированное поведение для MVP dev-режима. В prod необходимо убедиться, что `DEV_EMAIL_MODE` не установлен в `log`, иначе коды попадут в production логи.
- **Статус:** DEFERRED (V1 — настроить реальный email-провайдер)
- **Assignee:** BE

---

## P0-001: Нет `packages/ai/anonymizer.py`

- **Файл:** `packages/ai/` — модуль отсутствует
- **Описание:** `docs/ai/ANONYMIZER_RULES.md §5` описывает `packages/ai/anonymizer.py` с функцией `anonymize(text)`. AC-10 требует анонимизации PII в `ai_conversation_scores`. Модуль не создан в Wave 2. Тесты anonymizer пишутся против заглушки.
- **Статус:** OPEN — блокер для AC-10
- **Assignee:** BE (AI)

---

## P2-005: `search_path SET LOCAL` в export.py не защищён explicit schema prefix

- **Файл:** `apps/worker/worker/jobs/export.py:101`
- **Описание:** `SET LOCAL search_path = "{schema}", public` — используется `SET LOCAL`, что правильно. Однако в той же функции все INSERT-запросы не квалифицируются явным именем схемы (они опираются на `search_path`). Это корректно в рамках одной транзакции с `SET LOCAL`, но хрупко при рефакторинге.
- **Статус:** CLOSED (#52.7, 2026-04-22). В проде всё-таки выстрелило:
  bootstrap возвращал succeeded, следующий job падал с
  `UndefinedTable: relation "pipelines"/"raw_pipelines" does not exist`.
  Фикс:
  - `apps/api/app/db/migrations/tenant/env.py` — SA-native `execution_options(schema_translate_map={None: schema})` на Connection ДО `context.configure()`. `SET LOCAL` оставлен внутри alembic-транзакции как belt-and-suspenders.
  - `apps/worker/worker/jobs/export.py` + `apps/worker/worker/jobs/crm_pull.py` — все 12 INSERT'ов теперь schema-qualified (`INSERT INTO "<schema>".<table>`). Schema — строго валидированный идентификатор (`_validate_schema_name` в apply_tenant_template), инъекция исключена.
  - Регрессия: `tests/worker/test_bootstrap_then_pull_creates_data.py` — 4 integration-теста, гоняют полный пайплайн bootstrap → trial_export / pull_amocrm_core / build_export_zip(trial=True) против реального Postgres, проверяют `public.jobs.status='succeeded'` и физическое размещение таблиц в tenant-схеме.
- **Assignee:** DW (закрыто)

---

## P2-006: Дефолтные секреты JWT в settings.py

- **Файл:** `apps/api/app/core/settings.py:39-41`
- **Описание:** `jwt_secret` имеет дефолт `"dev-jwt-secret-change-me"`, `admin_jwt_secret` — `"dev-admin-jwt-secret-change-me"`. Если не переопределить в prod — возможна подделка JWT. Необходима валидация при старте: если `APP_ENV=production` и секрет == дефолту → fail-fast.
- **Статус:** OPEN
- **Assignee:** BE + LEAD
