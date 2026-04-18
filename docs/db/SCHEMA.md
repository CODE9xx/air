# DB Schema — Code9 Analytics

Этот документ описывает **целевую** схему БД на уровне MVP. Реализация — через alembic
миграции (ветвь `public/*` + tenant template). Стратегия — в `MIGRATION_STRATEGY.md`.

- Все `id` — `UUID` (gen через `uuid_generate_v4()` из `uuid-ossp` или `gen_random_uuid()` из `pgcrypto`).
- Все `created_at`, `updated_at` — `TIMESTAMPTZ NOT NULL DEFAULT NOW()`.
- Все `deleted_at` — nullable `TIMESTAMPTZ` (soft-delete, если явно указано).
- JSON — `JSONB`.
- Строки статусов — либо ENUM (предпочтительно), либо `TEXT` + CHECK.

## Именование

- **Main schema:** `public`.
- **Tenant schema:** `crm_<provider>_<8-char-lowercase-shortid>`,
  где `provider` ∈ `amo | kommo | bx24`, `shortid` — `substr(md5(random()), 1, 8)`.
  Пример: `crm_amo_a7f3c8e2`. **Создаётся** при переходе `crm_connections.status -> active`.
  **Удаляется** `DROP SCHEMA ... CASCADE` job'ом `delete_connection_data` при финальном удалении.
- Имя схемы хранится в `public.crm_connections.tenant_schema`.

---

# Часть 1. Main schema (`public`)

## 1.1 `users`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK, default gen_random_uuid() |
| `email` | CITEXT | UNIQUE, NOT NULL |
| `password_hash` | TEXT | NOT NULL (argon2id) |
| `display_name` | TEXT | NULL |
| `locale` | TEXT | NOT NULL DEFAULT 'ru', CHECK (`locale` IN ('ru','en')) |
| `email_verified_at` | TIMESTAMPTZ | NULL |
| `two_factor_enabled` | BOOLEAN | NOT NULL DEFAULT FALSE |
| `two_factor_secret_encrypted` | BYTEA | NULL (Fernet, только в V1) |
| `status` | TEXT | NOT NULL DEFAULT 'active', CHECK (`status` IN ('active','locked','deleted')) |
| `last_login_at` | TIMESTAMPTZ | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(email)` unique, `(status)`.

Комментарии: `users` — только обычные пользователи продукта. Для админов — `admin_users` (раздельно).

---

## 1.2 `user_sessions`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | FK→users(id) ON DELETE CASCADE, NOT NULL |
| `refresh_token_hash` | TEXT | NOT NULL (argon2 от opaque-токена) |
| `user_agent` | TEXT | NULL |
| `ip` | INET | NULL |
| `expires_at` | TIMESTAMPTZ | NOT NULL |
| `revoked_at` | TIMESTAMPTZ | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(user_id, revoked_at)`, `(expires_at)` для cleanup-job'а.

Комментарий: refresh-токен хранится ТОЛЬКО как argon2 hash. Opaque-часть видна только клиенту.

---

## 1.3 `email_verification_codes`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | FK→users(id) ON DELETE CASCADE, NOT NULL |
| `purpose` | TEXT | NOT NULL, CHECK (`purpose` IN ('email_verify','password_reset','connection_delete')) |
| `code_hash` | TEXT | NOT NULL (argon2id) |
| `attempts` | INT | NOT NULL DEFAULT 0 |
| `max_attempts` | INT | NOT NULL DEFAULT 5 |
| `metadata` | JSONB | NOT NULL DEFAULT '{}'::jsonb (например, `connection_id` для purpose=connection_delete) |
| `expires_at` | TIMESTAMPTZ | NOT NULL |
| `consumed_at` | TIMESTAMPTZ | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(user_id, purpose)`, `(expires_at)`.

---

## 1.4 `workspaces`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `name` | TEXT | NOT NULL |
| `slug` | TEXT | UNIQUE, NOT NULL |
| `owner_user_id` | UUID | FK→users(id), NOT NULL |
| `locale` | TEXT | NOT NULL DEFAULT 'ru', CHECK (`locale` IN ('ru','en')) |
| `industry` | TEXT | NULL (для AI-бенчмарков) |
| `status` | TEXT | NOT NULL DEFAULT 'active', CHECK (`status` IN ('active','paused','deleted')) |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `deleted_at` | TIMESTAMPTZ | NULL |

Индексы: `(slug)` unique, `(owner_user_id)`, `(status)`.

---

## 1.5 `workspace_members`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `workspace_id` | UUID | FK→workspaces(id) ON DELETE CASCADE, NOT NULL |
| `user_id` | UUID | FK→users(id) ON DELETE CASCADE, NOT NULL |
| `role` | TEXT | NOT NULL, CHECK (`role` IN ('owner','admin','analyst','viewer')) |
| `invited_by` | UUID | FK→users(id), NULL |
| `invited_at` | TIMESTAMPTZ | NULL |
| `accepted_at` | TIMESTAMPTZ | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

UNIQUE `(workspace_id, user_id)`. Индексы: `(user_id)`.

---

## 1.6 `crm_connections`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `workspace_id` | UUID | FK→workspaces(id) ON DELETE RESTRICT, NOT NULL |
| `provider` | TEXT | NOT NULL, CHECK (`provider` IN ('amocrm','kommo','bitrix24')) |
| `external_account_id` | TEXT | NULL (id аккаунта у CRM-провайдера) |
| `external_domain` | TEXT | NULL (например, `mycompany.amocrm.ru`) |
| `tenant_schema` | TEXT | NULL, UNIQUE WHEN NOT NULL |
| `status` | TEXT | NOT NULL DEFAULT 'pending', CHECK (`status` IN ('pending','connecting','active','paused','lost_token','deleting','deleted','error')) |
| `access_token_encrypted` | BYTEA | NULL (Fernet) |
| `refresh_token_encrypted` | BYTEA | NULL (Fernet) |
| `token_expires_at` | TIMESTAMPTZ | NULL |
| `last_sync_at` | TIMESTAMPTZ | NULL |
| `last_error` | TEXT | NULL |
| `metadata` | JSONB | NOT NULL DEFAULT '{}'::jsonb |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `deleted_at` | TIMESTAMPTZ | NULL |

Индексы: `(workspace_id)`, `(status)`, `(tenant_schema)` unique.

Комментарий: после `status=deleted` подключение не реактивируется. `tenant_schema` зануляется после DROP SCHEMA.

---

## 1.7 `billing_accounts`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `workspace_id` | UUID | FK→workspaces(id), UNIQUE, NOT NULL |
| `currency` | TEXT | NOT NULL DEFAULT 'RUB', CHECK (`currency` IN ('RUB','USD','EUR')) |
| `balance_cents` | BIGINT | NOT NULL DEFAULT 0 |
| `plan` | TEXT | NOT NULL DEFAULT 'free', CHECK (`plan` IN ('free','paygo','team')) |
| `provider` | TEXT | NOT NULL DEFAULT 'yookassa', CHECK (`provider` IN ('yookassa','stripe','manual')) |
| `external_customer_id` | TEXT | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(workspace_id)` unique.

---

## 1.8 `billing_ledger`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `billing_account_id` | UUID | FK→billing_accounts(id), NOT NULL |
| `workspace_id` | UUID | FK→workspaces(id), NOT NULL (денормализуем для retention) |
| `amount_cents` | BIGINT | NOT NULL (может быть отрицательным при списании) |
| `currency` | TEXT | NOT NULL |
| `kind` | TEXT | NOT NULL, CHECK (`kind` IN ('deposit','charge','refund','adjustment')) |
| `reference` | TEXT | NULL (id платежа провайдера / job'а) |
| `description` | TEXT | NULL |
| `metadata` | JSONB | NOT NULL DEFAULT '{}'::jsonb |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(billing_account_id, created_at DESC)`, `(workspace_id)`.

Комментарий: `billing_ledger` НЕ удаляется при удалении подключения/workspace — финансовая история хранится.

---

## 1.9 `jobs`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `workspace_id` | UUID | FK→workspaces(id) ON DELETE CASCADE, NULL (системные jobs могут быть без ws) |
| `crm_connection_id` | UUID | FK→crm_connections(id) ON DELETE SET NULL, NULL |
| `kind` | TEXT | NOT NULL, CHECK (`kind` IN ('fetch_crm_data','normalize_tenant_data','refresh_token','build_export_zip','run_audit_report','analyze_conversation','extract_patterns','anonymize_artifact','retention_warning','retention_read_only','retention_delete','delete_connection_data','recalc_balance','issue_invoice','bootstrap_tenant_schema')) |
| `queue` | TEXT | NOT NULL, CHECK (`queue` IN ('crm','export','audit','ai','retention','billing')) |
| `status` | TEXT | NOT NULL DEFAULT 'queued', CHECK (`status` IN ('queued','running','succeeded','failed','cancelled')) |
| `payload` | JSONB | NOT NULL DEFAULT '{}'::jsonb |
| `result` | JSONB | NULL |
| `error` | TEXT | NULL |
| `rq_job_id` | TEXT | NULL (id в RQ) |
| `started_at` | TIMESTAMPTZ | NULL |
| `finished_at` | TIMESTAMPTZ | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(workspace_id, created_at DESC)`, `(status, created_at DESC)`, `(rq_job_id)`.

---

## 1.10 `notifications`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `workspace_id` | UUID | FK→workspaces(id) ON DELETE CASCADE, NOT NULL |
| `user_id` | UUID | FK→users(id) ON DELETE CASCADE, NULL (NULL = всем членам ws) |
| `kind` | TEXT | NOT NULL, CHECK (`kind` IN ('sync_complete','sync_failed','export_ready','audit_ready','analysis_done','retention_warning','retention_read_only','retention_deleted','billing_low','connection_lost_token','connection_deleted')) |
| `title` | TEXT | NOT NULL |
| `body` | TEXT | NULL |
| `metadata` | JSONB | NOT NULL DEFAULT '{}'::jsonb |
| `read_at` | TIMESTAMPTZ | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(workspace_id, read_at NULLS FIRST, created_at DESC)`.

---

## 1.11 `admin_users`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `email` | CITEXT | UNIQUE, NOT NULL |
| `password_hash` | TEXT | NOT NULL (argon2id) |
| `display_name` | TEXT | NULL |
| `role` | TEXT | NOT NULL, CHECK (`role` IN ('superadmin','support','analyst')) |
| `status` | TEXT | NOT NULL DEFAULT 'active', CHECK (`status` IN ('active','locked','deleted')) |
| `last_login_at` | TIMESTAMPTZ | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(email)` unique.

Комментарий: полностью отдельная таблица от `users`, отдельный JWT secret (`ADMIN_JWT_SECRET`), scope=`admin`.

---

## 1.12 `admin_audit_logs`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `admin_user_id` | UUID | FK→admin_users(id), NOT NULL |
| `action` | TEXT | NOT NULL (например: `workspace_pause`, `connection_resume`, `billing_adjustment`, `support_mode_read_tenant`, `job_restart`, `admin_login`) |
| `target_type` | TEXT | NULL (`workspace` / `connection` / `billing_account` / `job` / `user`) |
| `target_id` | UUID | NULL |
| `metadata` | JSONB | NOT NULL DEFAULT '{}'::jsonb (включает `reason` для support-mode) |
| `ip` | INET | NULL |
| `user_agent` | TEXT | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(admin_user_id, created_at DESC)`, `(action)`, `(target_type, target_id)`.

Комментарий: пишется в **той же транзакции**, что и само действие (см. ADR-008). Лог не удаляется даже при удалении workspace.

---

## 1.13 `deletion_requests`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `crm_connection_id` | UUID | FK→crm_connections(id), NOT NULL |
| `requested_by_user_id` | UUID | FK→users(id), NOT NULL |
| `status` | TEXT | NOT NULL DEFAULT 'awaiting_code', CHECK (`status` IN ('awaiting_code','confirmed','cancelled','expired','completed')) |
| `email_code_hash` | TEXT | NOT NULL (argon2id от 6-значного кода) |
| `attempts` | INT | NOT NULL DEFAULT 0 |
| `max_attempts` | INT | NOT NULL DEFAULT 5 |
| `expires_at` | TIMESTAMPTZ | NOT NULL (TTL 10 min) |
| `confirmed_at` | TIMESTAMPTZ | NULL |
| `completed_at` | TIMESTAMPTZ | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(crm_connection_id, status)`, `(expires_at)`.

---

## 1.14 AI-таблицы (main schema)

### 1.14.1 `ai_analysis_jobs`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `workspace_id` | UUID | FK→workspaces(id) ON DELETE CASCADE, NOT NULL |
| `crm_connection_id` | UUID | FK→crm_connections(id) ON DELETE SET NULL, NULL |
| `kind` | TEXT | NOT NULL, CHECK (`kind` IN ('call_transcript','chat_dialog','deal_review')) |
| `input_ref` | JSONB | NOT NULL (ссылки на tenant-объекты: `{call_id, deal_id, ...}`) |
| `prompt_version_id` | UUID | FK→ai_prompt_versions(id), NULL |
| `model_run_id` | UUID | FK→ai_model_runs(id), NULL |
| `status` | TEXT | NOT NULL DEFAULT 'queued', CHECK (`status` IN ('queued','running','succeeded','failed','cancelled')) |
| `error` | TEXT | NULL |
| `started_at` | TIMESTAMPTZ | NULL |
| `finished_at` | TIMESTAMPTZ | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(workspace_id, created_at DESC)`, `(status)`.

### 1.14.2 `ai_conversation_scores`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `analysis_job_id` | UUID | FK→ai_analysis_jobs(id) ON DELETE CASCADE, NOT NULL |
| `workspace_id` | UUID | FK→workspaces(id) ON DELETE CASCADE, NOT NULL |
| `overall_score` | NUMERIC(5,2) | NULL (0..100) |
| `dimension_scores` | JSONB | NOT NULL DEFAULT '{}'::jsonb (greeting, needs_discovery, objection_handling, closing, …) |
| `strengths` | JSONB | NOT NULL DEFAULT '[]'::jsonb |
| `weaknesses` | JSONB | NOT NULL DEFAULT '[]'::jsonb |
| `recommendations` | JSONB | NOT NULL DEFAULT '[]'::jsonb |
| `confidence` | NUMERIC(3,2) | NULL (0..1) |
| `raw_llm_output` | JSONB | NULL (для отладки, удаляется retention'ом при privacy_risk=high) |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(workspace_id, created_at DESC)`, `(analysis_job_id)`.

### 1.14.3 `ai_behavior_patterns`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `workspace_id` | UUID | FK→workspaces(id) ON DELETE CASCADE, NOT NULL |
| `pattern_type` | TEXT | NOT NULL (`missed_need`, `objection_unhandled`, `no_next_step`, `long_silence`, …) |
| `frequency_bucket` | TEXT | NOT NULL, CHECK (`frequency_bucket` IN ('low','medium','high')) |
| `sample_size` | INT | NOT NULL |
| `description` | TEXT | NOT NULL |
| `evidence_refs` | JSONB | NOT NULL DEFAULT '[]'::jsonb (tenant-level refs, не raw transcript) |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(workspace_id, pattern_type)`. Ограничение: `sample_size >= 10` (CHECK).

### 1.14.4 `ai_client_knowledge_items`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `workspace_id` | UUID | FK→workspaces(id) ON DELETE CASCADE, NOT NULL |
| `source` | TEXT | NOT NULL, CHECK (`source` IN ('manual','extracted_from_cases','uploaded_doc')) |
| `title` | TEXT | NOT NULL |
| `body` | TEXT | NOT NULL |
| `version_id` | UUID | FK→ai_prompt_versions(id), NULL (для связывания со сборкой KB) |
| `status` | TEXT | NOT NULL DEFAULT 'active', CHECK (`status` IN ('active','archived')) |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(workspace_id, status)`.

### 1.14.5 `ai_research_consent`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `workspace_id` | UUID | FK→workspaces(id) ON DELETE CASCADE, UNIQUE, NOT NULL |
| `status` | TEXT | NOT NULL DEFAULT 'not_asked', CHECK (`status` IN ('not_asked','accepted','revoked')) |
| `accepted_at` | TIMESTAMPTZ | NULL |
| `revoked_at` | TIMESTAMPTZ | NULL |
| `accepted_by_user_id` | UUID | FK→users(id), NULL |
| `terms_version` | TEXT | NULL |
| `metadata` | JSONB | NOT NULL DEFAULT '{}'::jsonb |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(workspace_id)` unique.

### 1.14.6 `ai_research_patterns` (агрегированные анонимизированные)

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `industry` | TEXT | NULL |
| `pattern_type` | TEXT | NOT NULL |
| `channel` | TEXT | NULL (`call` / `chat` / `email`) |
| `objection_type` | TEXT | NULL |
| `response_type` | TEXT | NULL |
| `duration_bucket` | TEXT | NULL (`0-30s`, `30-120s`, `2-5m`, `5-15m`, `15m+`) |
| `period_bucket` | TEXT | NULL (`week`, `month`, `quarter`) |
| `sample_size` | INT | NOT NULL, CHECK (`sample_size >= 10`) |
| `confidence` | NUMERIC(3,2) | NULL |
| `summary` | TEXT | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(industry, pattern_type)`, `(period_bucket)`.

Комментарий: никаких FK на workspace/user — это агрегат по consent-положительным workspace'ам, де-идентифицирован.

### 1.14.7 `ai_prompt_versions`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `key` | TEXT | NOT NULL (например `score_call`, `extract_pattern`) |
| `version` | INT | NOT NULL |
| `template` | TEXT | NOT NULL |
| `params` | JSONB | NOT NULL DEFAULT '{}'::jsonb |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

UNIQUE `(key, version)`. Индексы: `(key, is_active)`.

### 1.14.8 `ai_model_runs`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `provider` | TEXT | NOT NULL, CHECK (`provider` IN ('openai','anthropic','mock')) |
| `model` | TEXT | NOT NULL |
| `prompt_version_id` | UUID | FK→ai_prompt_versions(id), NULL |
| `input_tokens` | INT | NULL |
| `output_tokens` | INT | NULL |
| `latency_ms` | INT | NULL |
| `cost_cents` | INT | NULL |
| `status` | TEXT | NOT NULL, CHECK (`status` IN ('ok','error','timeout')) |
| `error` | TEXT | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(provider, model, created_at DESC)`.

---

# Часть 2. Tenant schema template (`crm_<provider>_<shortid>`)

Создаётся job'ом `bootstrap_tenant_schema` при активации подключения. Все таблицы живут внутри этой схемы. FK — локальные (внутри схемы), а не кросс-schema.

## 2.1 Raw tables (как пришло из CRM)

Общий паттерн для всех `raw_*`:

| Поле | Тип |
|---|---|
| `id` | UUID PK |
| `external_id` | TEXT NOT NULL |
| `payload` | JSONB NOT NULL |
| `fetched_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() |
| `source_event_id` | TEXT NULL (для дедупликации) |

UNIQUE `(external_id)` (в рамках схемы).

Список raw-таблиц:
- `raw_deals`
- `raw_contacts`
- `raw_companies`
- `raw_tasks`
- `raw_notes`
- `raw_events`
- `raw_calls`
- `raw_chats`
- `raw_messages`
- `raw_users`
- `raw_pipelines`
- `raw_stages`
- `raw_products`
- `raw_tags`

## 2.2 Normalized tables

Нормализация — из `raw_*` в структурированные колонки для быстрых дашбордов/запросов.

### `deals`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `external_id` | TEXT | UNIQUE, NOT NULL |
| `name` | TEXT | NULL |
| `pipeline_id` | UUID | FK→pipelines(id), NULL |
| `stage_id` | UUID | FK→stages(id), NULL |
| `status` | TEXT | NULL (`open`/`won`/`lost`) |
| `responsible_user_id` | UUID | FK→crm_users(id), NULL |
| `contact_id` | UUID | FK→contacts(id), NULL |
| `company_id` | UUID | FK→companies(id), NULL |
| `price_cents` | BIGINT | NULL |
| `currency` | TEXT | NULL |
| `created_at_external` | TIMESTAMPTZ | NULL |
| `updated_at_external` | TIMESTAMPTZ | NULL |
| `closed_at_external` | TIMESTAMPTZ | NULL |
| `fetched_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(pipeline_id, stage_id)`, `(status)`, `(responsible_user_id)`.

### `contacts`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `external_id` | TEXT | UNIQUE |
| `full_name` | TEXT | NULL |
| `phone_primary_hash` | TEXT | NULL (SHA-256, оригинал в raw.payload) |
| `email_primary_hash` | TEXT | NULL |
| `responsible_user_id` | UUID | FK→crm_users(id), NULL |
| `created_at_external` | TIMESTAMPTZ | NULL |
| `fetched_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(phone_primary_hash)`, `(email_primary_hash)`, `(responsible_user_id)`.

### `companies`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `external_id` | TEXT | UNIQUE |
| `name` | TEXT | NULL |
| `inn_hash` | TEXT | NULL |
| `created_at_external` | TIMESTAMPTZ | NULL |
| `fetched_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

### `tasks`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `external_id` | TEXT | UNIQUE |
| `deal_id` | UUID | FK→deals(id), NULL |
| `responsible_user_id` | UUID | FK→crm_users(id), NULL |
| `kind` | TEXT | NULL |
| `text` | TEXT | NULL |
| `is_completed` | BOOLEAN | NOT NULL DEFAULT FALSE |
| `due_at_external` | TIMESTAMPTZ | NULL |
| `completed_at_external` | TIMESTAMPTZ | NULL |
| `fetched_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(deal_id)`, `(responsible_user_id, is_completed)`, `(due_at_external)`.

### `notes`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `external_id` | TEXT | UNIQUE |
| `deal_id` | UUID | FK→deals(id), NULL |
| `contact_id` | UUID | FK→contacts(id), NULL |
| `author_user_id` | UUID | FK→crm_users(id), NULL |
| `body` | TEXT | NULL |
| `created_at_external` | TIMESTAMPTZ | NULL |
| `fetched_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

### `calls`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `external_id` | TEXT | UNIQUE |
| `deal_id` | UUID | FK→deals(id), NULL |
| `contact_id` | UUID | FK→contacts(id), NULL |
| `user_id` | UUID | FK→crm_users(id), NULL |
| `direction` | TEXT | CHECK (`direction` IN ('in','out')) |
| `duration_sec` | INT | NULL |
| `result` | TEXT | NULL |
| `started_at_external` | TIMESTAMPTZ | NULL |
| `transcript_ref` | JSONB | NULL (эфемерная ссылка, аудио не храним) |
| `fetched_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(deal_id)`, `(user_id, started_at_external)`.

### `chats`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `external_id` | TEXT | UNIQUE |
| `channel` | TEXT | NULL (`whatsapp`/`telegram`/`site`/`email`) |
| `deal_id` | UUID | FK→deals(id), NULL |
| `contact_id` | UUID | FK→contacts(id), NULL |
| `started_at_external` | TIMESTAMPTZ | NULL |
| `closed_at_external` | TIMESTAMPTZ | NULL |
| `fetched_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

### `messages`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `external_id` | TEXT | UNIQUE |
| `chat_id` | UUID | FK→chats(id), NULL |
| `author_kind` | TEXT | CHECK (`author_kind` IN ('user','client','system')) |
| `author_user_id` | UUID | FK→crm_users(id), NULL |
| `text` | TEXT | NULL |
| `sent_at_external` | TIMESTAMPTZ | NULL |
| `fetched_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(chat_id, sent_at_external)`.

### `pipelines`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `external_id` | TEXT | UNIQUE |
| `name` | TEXT | NOT NULL |
| `is_default` | BOOLEAN | NOT NULL DEFAULT FALSE |
| `fetched_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

### `stages`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `external_id` | TEXT | UNIQUE |
| `pipeline_id` | UUID | FK→pipelines(id), NOT NULL |
| `name` | TEXT | NOT NULL |
| `sort_order` | INT | NULL |
| `kind` | TEXT | NULL (`open`/`won`/`lost`) |
| `fetched_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Индексы: `(pipeline_id, sort_order)`.

### `crm_users`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `external_id` | TEXT | UNIQUE |
| `full_name` | TEXT | NULL |
| `email_hash` | TEXT | NULL |
| `role` | TEXT | NULL |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE |
| `fetched_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

### `products`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `external_id` | TEXT | UNIQUE |
| `name` | TEXT | NULL |
| `price_cents` | BIGINT | NULL |
| `currency` | TEXT | NULL |
| `fetched_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

### `tags`

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `external_id` | TEXT | UNIQUE |
| `name` | TEXT | NOT NULL |
| `fetched_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

### `deal_tags` (join)

| Поле | Тип | Констрейнты |
|---|---|---|
| `deal_id` | UUID | FK→deals(id) ON DELETE CASCADE, NOT NULL |
| `tag_id` | UUID | FK→tags(id) ON DELETE CASCADE, NOT NULL |

PK `(deal_id, tag_id)`.

### `knowledge_base_versions`

Хранит снэпшот БЗ клиента на момент анализа (например, скрипт продаж, описание продукта). Используется AI-анализатором для сверки.

| Поле | Тип | Констрейнты |
|---|---|---|
| `id` | UUID | PK |
| `version` | INT | NOT NULL |
| `content` | TEXT | NOT NULL |
| `metadata` | JSONB | NOT NULL DEFAULT '{}'::jsonb |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

UNIQUE `(version)`. Индексы: `(is_active, created_at DESC)`.

---

# Часть 3. Enum-значения (сводно)

| Enum | Значения |
|---|---|
| `user.status` | `active`, `locked`, `deleted` |
| `user.locale` | `ru`, `en` |
| `workspace.status` | `active`, `paused`, `deleted` |
| `workspace_member.role` | `owner`, `admin`, `analyst`, `viewer` |
| `email_verification_codes.purpose` | `email_verify`, `password_reset`, `connection_delete` |
| `crm_connection.provider` | `amocrm`, `kommo`, `bitrix24` |
| `crm_connection.status` | `pending`, `connecting`, `active`, `paused`, `lost_token`, `deleting`, `deleted`, `error` |
| `billing_account.currency` | `RUB`, `USD`, `EUR` |
| `billing_account.plan` | `free`, `paygo`, `team` |
| `billing_account.provider` | `yookassa`, `stripe`, `manual` |
| `billing_ledger.kind` | `deposit`, `charge`, `refund`, `adjustment` |
| `jobs.kind` | см. CHECK в 1.9 |
| `jobs.queue` | `crm`, `export`, `audit`, `ai`, `retention`, `billing` |
| `jobs.status` | `queued`, `running`, `succeeded`, `failed`, `cancelled` |
| `notifications.kind` | см. CHECK в 1.10 |
| `admin_users.role` | `superadmin`, `support`, `analyst` |
| `deletion_requests.status` | `awaiting_code`, `confirmed`, `cancelled`, `expired`, `completed` |
| `ai_analysis_jobs.kind` | `call_transcript`, `chat_dialog`, `deal_review` |
| `ai_analysis_jobs.status` | `queued`, `running`, `succeeded`, `failed`, `cancelled` |
| `ai_behavior_patterns.frequency_bucket` | `low`, `medium`, `high` |
| `ai_client_knowledge_items.source` | `manual`, `extracted_from_cases`, `uploaded_doc` |
| `ai_client_knowledge_items.status` | `active`, `archived` |
| `ai_research_consent.status` | `not_asked`, `accepted`, `revoked` |
| `ai_model_runs.provider` | `openai`, `anthropic`, `mock` |
| `ai_model_runs.status` | `ok`, `error`, `timeout` |
| tenant `calls.direction` | `in`, `out` |
| tenant `messages.author_kind` | `user`, `client`, `system` |
| tenant `stages.kind` | `open`, `won`, `lost` |
