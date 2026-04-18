# Architecture — Code9 Analytics

## 1. Контекст

Code9 Analytics — multi-tenant SaaS. Внутри платформы:
- пользователи принадлежат workspace'ам;
- workspace подключает одну или несколько CRM (amoCRM / Kommo / Bitrix24) через OAuth;
- каждое подключение изолировано в отдельную Postgres schema;
- долгие операции (синхронизация CRM, экспорт, AI-анализ, retention, рассылка отчётов) выполняются фоновым worker'ом через Redis/RQ.

## 2. Топология сервисов (dev)

```
                 +---------+        +----------+
  browser  <-->  |  web    |  API   |   api    | <----> postgres
  (3000)         | (Next14)|  JSON  | (FastAPI)|   |    (5432)
                 +---------+        +----------+   |
                                        |          |
                                        v          v
                                     +-------+
                                     | redis |
                                     | (6379)|
                                     +-------+
                                        ^
                                        |
                                     +---------+
                                     | worker  |
                                     |  (RQ)   |
                                     +---------+
```

Подробности — в `docker-compose.yml`.

## 3. Компоненты

### 3.1 `apps/web` — Next.js 14
- Layout, роутинг, i18n (RU+EN) через `next-intl`.
- Auth-flow (login/register/verify), workspace UI, CRM connections, аудит, экспорт, дашборды, billing, AI, admin panel.
- Токены: access в памяти, refresh в httpOnly secure cookie (детали — `security/AUTH.md`).
- Не держит серверной бизнес-логики: всё через REST к `apps/api`.

### 3.2 `apps/api` — FastAPI
- REST API, контракт — `api/CONTRACT.md`.
- Auth + rate-limit на Redis (sliding window).
- CRUD для `public.*`-таблиц.
- Enqueue jobs в Redis (`crm`, `export`, `audit`, `ai`, `retention`, `billing`).
- Никогда не делает долгих IO внутри request cycle.

### 3.3 `apps/worker` — RQ worker
- Слушает очереди, выполняет job-функции.
- Типичные job'ы: `fetch_crm_data`, `refresh_token`, `build_export_zip`, `run_audit_report`, `analyze_conversation`, `retention_*`, `delete_connection_data`.
- Single entrypoint (`worker/main.py`), при необходимости можно масштабировать до N реплик.

### 3.4 Postgres 18
- Main schema `public`.
- Tenant schemas `crm_<provider>_<8-char-lowercase-shortid>` (создаются/удаляются worker'ом).
- Полная схема — `db/SCHEMA.md`.

### 3.5 Redis 7
- RQ queues.
- Rate-limit counters.
- Short-lived cache (email-verification попытки, OAuth state).

### 3.6 `packages/crm-connectors`
- Единый интерфейс `CRMConnector`: `fetch_deals(...)`, `fetch_contacts(...)`, `refresh_token(...)`.
- Реализации: `AmoCRMConnector`, `KommoConnector`, `Bitrix24Connector`, `MockCRMConnector`.
- При `MOCK_CRM_MODE=true` — используется `MockCRMConnector` с фикстурами.

### 3.7 `packages/ai`
- Промпт-шаблоны (`ai_prompt_versions`).
- Анонимайзер (`ai/ANONYMIZER_RULES.md`).
- LLM-gateway (в MVP — mock, возвращает детерминированный JSON).

## 4. Потоки данных

### 4.1 CRM connect + first sync
```
user → web → api POST /crm/connections
  → (если MOCK_CRM_MODE) api создаёт row в public.crm_connections (status=active)
  → enqueue job "bootstrap_tenant_schema" (worker создаёт schema из template)
  → enqueue job "fetch_crm_data" (worker тянет raw_* через MockCRMConnector)
  → job "normalize_tenant_data" (raw_* → normalized)
  → notification "sync_complete"
```

### 4.2 Экспорт
```
user → POST /export/jobs → api кладёт row в public.jobs (status=queued)
  → worker: build_export_zip → складывает файлы в volume
  → notification с download-URL (подписанный, TTL)
  → retention cleanup через N часов
```

### 4.3 AI-анализ разговора
```
user → POST /ai/analysis-jobs → api создаёт ai_analysis_jobs row, enqueue
  → worker: получает аудио/текст, анонимизирует, отправляет в LLM (mock)
  → worker: сохраняет ai_conversation_scores, при consent=accepted — ai_behavior_patterns
  → notification "analysis_done"
  → аудио НЕ хранится, удаляется после job'а
```

### 4.4 Deletion flow
```
user → POST /crm/connections/:id/delete/request
  → api создаёт deletion_requests (awaiting_code), отправляет email-код (dev: в лог)
user → POST /crm/connections/:id/delete/confirm {code}
  → api проверяет hash, статус → confirmed, enqueue delete_connection_data
  → worker: connection.status = deleting → DROP SCHEMA ... CASCADE → status = deleted
  → public.billing_ledger и admin_audit_logs сохраняются
  → notification "deleted"
```

## 5. Безопасность (сводно)

- Пароли: argon2id (par=2, mem=64MB, iter=3).
- Access JWT HS256, 15 min TTL. Refresh — opaque token в `user_sessions`, 30 дней.
- OAuth-токены CRM — Fernet at rest, никогда не в API/UI/логах.
- Destructive actions — email-код + argon2 hash.
- Admin — отдельная таблица `admin_users`, отдельный `ADMIN_JWT_SECRET`, scope=`admin`.
- Admin support mode — доступ к tenant raw только при явном toggle с reason.

Подробно — в `security/*.md`.

## 6. Приватность и retention

- Retention days: 0/1/7/30/60/75/85/90 (см. `security/RETENTION_POLICY.md`).
- Аудио не хранится (только эфемерно внутри job'а).
- Файлы/картинки из CRM не импортируем.
- AI-исследование — только по explicit consent, с анонимизацией и min sample_size=10.

## 7. Наблюдаемость (Wave 2+)

- `structlog` JSON в stdout (собирается платформой хостинга).
- Трейсы — OpenTelemetry, V1.
- Alarms — email/Telegram, V1.

## 8. Что НЕ входит в MVP

- Реальный OAuth amoCRM/Kommo/Bitrix24 (используются mock-адаптеры).
- Реальный YooKassa/Stripe (billing pipeline работает на mock webhook'ах).
- Реальный LLM (OpenAI/Anthropic; используется локальный mock-gateway).
- 2FA UX (поля в БД есть, логика — V1).
- Кэш sync CRM между клиентами (в MVP каждый клиент дёргает свою CRM независимо).
- SSO (Google/Yandex/Apple).
