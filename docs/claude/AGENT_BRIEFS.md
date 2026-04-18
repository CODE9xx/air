# Agent Briefs — Wave 2

Короткие брифы, которые оркестратор вставит в prompt каждому sub-агенту Wave 2.
Все брифы опираются на документы Wave 1, которые уже существуют в `docs/`.

Общие правила для всех агентов Wave 2:

- **Нельзя** трогать файлы вне своей зоны — см. `docs/architecture/FILE_OWNERSHIP.md`.
- Для правки чужой зоны — CR в `docs/architecture/CHANGE_REQUESTS.md` → approval Lead + owner.
- Читать контракты из `docs/api/CONTRACT.md`, схему из `docs/db/SCHEMA.md`, безопасность из `docs/security/*.md`.
- `MOCK_CRM_MODE=true` всегда в MVP. Никаких реальных HTTP в amoCRM/YooKassa/Stripe/LLM.
- Комментарии и docstring — RU.
- Тесты не пишет (это QA), но код должен быть тестируем.
- Все долгие операции — через worker jobs, не в request cycle.

---

## Brief 1 — Backend Engineer (BE)

**Цель Wave 2:** реализовать FastAPI endpoints по `docs/api/CONTRACT.md`, модели SA для public-схемы, rate-limit, auth, enqueue-логику для jobs.

**Зона файлов:** `apps/api/app/**` (кроме `db/migrations/`), `apps/api/pyproject.toml`, `packages/ai/**`, `packages/shared/**` (совместно с FE через CR).

**Запрещённые зоны:** `apps/web/**`, `apps/worker/**`, `packages/crm-connectors/**`, `infra/**`, `docker-compose.yml`, `.env.example`, `docs/**`.

**Зависимости (читать):**
- `docs/api/CONTRACT.md` — финальный контракт endpoints.
- `docs/db/SCHEMA.md` — модели и enum.
- `docs/security/AUTH.md` — пароли/JWT/refresh/2FA.
- `docs/security/OAUTH_TOKENS.md` — шифрование токенов.
- `docs/security/DELETION_FLOW.md` — deletion flow.
- `docs/security/ADMIN_SUPPORT_MODE.md` — админ auth + support-mode.

**Структура (целевая):**
```
apps/api/app/
  core/ (settings, logging, redis, db, security-utils, rate-limit)
  auth/ (routers, services, schemas, dependencies)
  users/, workspaces/, crm/, dashboards/, billing/, jobs/, ai/, admin/, notifications/
  db/models/
```

**Acceptance:**
- Все endpoints в `CONTRACT.md` существуют и возвращают правильный формат.
- Rate-limit работает как в `AUTH.md`.
- Нет логов с реальными токенами.
- `MOCK_CRM_MODE=true` — создаётся connection без реального OAuth за <2s.

**Команды:**
```
docker compose up api
curl http://localhost:8000/api/v1/health
```

**Deliverables:** рабочий API, 40+ endpoints, passing QA-чек-лист секций 1-11,13.

---

## Brief 2 — Frontend Engineer (FE)

**Цель Wave 2:** Next.js 14 App Router с i18n (RU+EN), auth-flow, workspace/connection UI, дашборды, admin panel.

**Зона файлов:** `apps/web/**`, `packages/shared/**` (совместно с BE).

**Запрещённые зоны:** все `apps/api/**`, `apps/worker/**`, `packages/crm-connectors/**`, `infra/**`, `docs/**` (кроме QA-обсуждений в CR).

**Зависимости:**
- `docs/api/CONTRACT.md` — все запросы.
- `docs/security/AUTH.md` — cookie refresh, access в памяти.

**Структура:**
```
apps/web/
  app/ (layout, page, [locale]/, dashboard/, admin/)
  middleware.ts (next-intl)
  messages/ru.json, messages/en.json
  components/
  lib/api.ts (typed client)
```

**Acceptance:**
- RU/EN переключатель работает.
- Auth-flow end-to-end.
- Нет хардкод-строк в компонентах (grep проверяет QA).
- Токены: access в памяти, refresh — только в cookie (не в localStorage).

**Команды:**
```
docker compose up web
open http://localhost:3000
```

**Deliverables:** работающий UI по чек-листу QA секций 2-11,14.

---

## Brief 3 — DB & Worker Engineer (DW)

**Цель Wave 2:** alembic миграции (main + tenant template), RQ worker с 6 очередями, job-функции, retention-scheduler.

**Зона файлов:** `apps/worker/**`, `apps/api/app/db/migrations/**`, `scripts/seed/**`, `scripts/migrations/**`.

**Совместно через CR:** `apps/api/app/db/models/**` (с BE), `apps/api/app/jobs/**` (имена очередей/job-функций — с BE).

**Запрещённые зоны:** `apps/web/**`, `packages/crm-connectors/**`, `infra/**`, `docs/architecture/**`.

**Зависимости:**
- `docs/db/SCHEMA.md` — обе части (main + tenant).
- `docs/db/MIGRATION_STRATEGY.md` — два alembic env'а.
- `docs/security/RETENTION_POLICY.md` — календарь retention.
- `docs/security/DELETION_FLOW.md` — job `delete_connection_data`.
- `docs/security/OAUTH_TOKENS.md` — шифрование в `refresh_token` job.

**Структура worker:**
```
apps/worker/worker/
  main.py (RQ Worker, listens 6 queues)
  jobs/crm.py, export.py, audit.py, ai.py, retention.py, billing.py
  lib/crypto.py (Fernet wrapper), lib/db.py
```

**Ключевые jobs:**
`fetch_crm_data`, `normalize_tenant_data`, `refresh_token`, `build_export_zip`,
`run_audit_report`, `analyze_conversation`, `extract_patterns`, `anonymize_artifact`,
`retention_warning`, `retention_read_only`, `retention_delete`, `delete_connection_data`,
`recalc_balance`, `issue_invoice`, `bootstrap_tenant_schema`.

**Acceptance:**
- `alembic upgrade head` для main + tenant — идемпотентно.
- Worker обрабатывает все типы job'ов.
- `scripts/seed/seed_admin.py` — bootstrap-админ создан по env.
- Retention-scheduler запускает daily-job'ы (rq-scheduler).

**Команды:**
```
docker compose up worker
docker compose exec api alembic -c apps/api/app/db/migrations/main/alembic.ini upgrade head
```

**Deliverables:** миграции + живой worker + seed-скрипты. QA-чек-лист секций 6,7,12,14,15.

---

## Brief 4 — CRM Integration Engineer (CRM)

**Цель Wave 2:** `packages/crm-connectors` — единый интерфейс `CRMConnector`, реализации для amoCRM/Kommo/Bitrix24, а также `MockCRMConnector` с фикстурами.

**Зона файлов:** `packages/crm-connectors/**`.

**Совместно через CR:** `apps/api/app/crm/` (только контракт коннекторов — с BE).

**Запрещённые зоны:** все `apps/api/**` (кроме CR-обсуждений), `apps/web/**`, `apps/worker/**`, `infra/**`, `docs/**`.

**Зависимости:**
- `docs/api/CONTRACT.md` — endpoints `/crm/oauth/*`.
- `docs/security/OAUTH_TOKENS.md` — refresh в worker'е.
- `docs/db/SCHEMA.md` — raw_* таблицы.

**Структура:**
```
packages/crm-connectors/
  src/
    base.py (CRMConnector interface, TypedDict'ы)
    amocrm.py, kommo.py, bitrix24.py, mock.py
  fixtures/
    amo_deals.json, amo_contacts.json, ...
  pyproject.toml
```

**Интерфейс (черновой):**
```python
class CRMConnector(Protocol):
    provider: Literal["amocrm","kommo","bitrix24","mock"]
    def oauth_authorize_url(self, state: str) -> str: ...
    def exchange_code(self, code: str) -> TokenPair: ...
    def refresh(self, refresh_token: str) -> TokenPair: ...
    def fetch_deals(self, access_token: str, since: datetime|None) -> Iterable[RawDeal]: ...
    # ... и т.д. для всех raw_*
```

**MockCRMConnector:** возвращает фикстуры из `fixtures/`. При `MOCK_CRM_MODE=true` API/worker используют его.

**Acceptance:**
- Единый интерфейс, совместимый между всеми провайдерами.
- Mock возвращает ≥10 deals, ≥20 contacts, ≥10 calls, ≥5 tasks, ≥5 pipelines×stages.
- Pagination-awareness (`since`/`cursor` параметры).

**Команды:**
```
docker compose exec worker python -c "from crm_connectors.mock import MockCRMConnector; print(len(list(MockCRMConnector().fetch_deals('x', None))))"
```

**Deliverables:** Mock коннектор работает в end-to-end sync. Реальные — скелеты (HTTP-обёртки без полной реализации, V1).

---

## Brief 5 — QA Engineer (QA)

**Цель Wave 2:** тесты (unit + integration), прохождение `docs/qa/MANUAL_TEST_CHECKLIST.md`, валидация `docs/qa/ACCEPTANCE_CRITERIA.md`.

**Зона файлов:** `tests/**`, `docs/qa/**`.

**Запрещённые зоны:** production-код (нельзя менять `apps/**`, `packages/**`, `infra/**`).

**Зависимости:**
- `docs/qa/ACCEPTANCE_CRITERIA.md` — что проверять.
- `docs/qa/MANUAL_TEST_CHECKLIST.md` — ручной чек-лист.
- `docs/security/AUTH.md`, `DELETION_FLOW.md`, `ADMIN_SUPPORT_MODE.md` — security-assertions.
- `docs/ai/ANONYMIZER_RULES.md` — PII-regex-проверки.

**Структура тестов:**
```
tests/
  api/ (pytest, httpx, async — against docker-compose)
    test_auth.py, test_workspace.py, test_crm_connections.py, test_ai.py, test_admin.py
  security/
    test_token_leak.py (grep-style ассерты по логам)
    test_anonymizer.py (golden corpus)
  e2e/
    test_connect_sync_audit.py
```

**Acceptance:**
- Все AC в `ACCEPTANCE_CRITERIA.md` покрыты хотя бы одним тестом.
- PII-regex тесты не ломаются на 100 случайных семплах LLM-выхода.
- CI-prompt — `pytest tests/` под docker-compose test-профилем.

**Команды:**
```
docker compose up -d postgres redis api worker
docker compose exec api pytest -q
```

**Deliverables:** passing test suite + актуальный чек-лист + баг-репорты (в issues/trello — по договорённости с оркестратором).
