# Acceptance Criteria — Code9 Analytics MVP

Каждая секция — короткие «definition of done» для приёмки фичи. Owner формулировки — Lead + QA.

## AC-0. Scaffold (Wave 1)

- `docker compose up --build` поднимает 5 контейнеров без ошибок.
- `curl http://localhost:8000/` → `{"service":"code9-api",...}`.
- `curl http://localhost:8000/health` → `{"status":"ok"}`.
- `curl http://localhost:3000/health` → `{"status":"ok"}`.
- Postgres внутри `code9-postgres` отвечает `pg_isready`.
- Redis внутри `code9-redis` отвечает `PONG`.
- Воркер в логах пишет `[worker] heartbeat #N`.

## AC-1. Auth

- Регистрация: `POST /auth/register` с корректными данными → 201, email создан, `email_verified_at=NULL`.
- Email verify: код приходит в лог api (DEV), после `POST /auth/verify-email/confirm` — `email_verified=true`.
- Login: без verify → 401 `email_not_verified`; с verify → 200 + cookie `code9_refresh`.
- Refresh: старый access истёк, `POST /auth/refresh` с cookie → новый access.
- Logout: refresh row получает `revoked_at`.
- Rate-limit login: после 6 неудач с одного IP за минуту → 429.
- Password reset: flow work end-to-end.

## AC-2. Workspace

- Только зарегистрированный user может создать workspace.
- Owner может пригласить пользователя по email; invited — в статусе pending до accept.
- Удалить workspace в MVP нельзя (pause — можно; deletion — V1).

## AC-3. CRM Connection (mock)

- `POST /workspaces/:wsid/crm/connections` с `provider=amocrm`, `MOCK_CRM_MODE=true` → status=active за <2s, tenant schema создана.
- `GET /workspaces/:wsid/crm/connections` — токены НЕ видны в ответе.
- `POST /crm/connections/:id/sync` → job `fetch_crm_data` выполнился → tenant `raw_deals` содержит >=10 фикстурных записей → normalized `deals` >= 10.
- `POST /crm/connections/:id/pause` → status=paused, новые sync-job'ы не запускаются.
- Delete flow: request → код в логе → confirm → за ≤30s `status=deleted`, schema DROPPED, токены = NULL.

## AC-4. Audit

- `POST /workspaces/:wsid/audit/reports` с активным connection → job выполнился → report доступен через GET за ≤15s.
- Отчёт содержит ≥5 метрик (просроченные задачи, дубли, незаполненные обязательные поля, брошенные сделки, etc).

## AC-5. Export

- `POST /workspaces/:wsid/export/jobs` → job_id → статус `succeeded` за ≤60s.
- `download_url` выдаётся с TTL и подписанным токеном.
- Содержимое ZIP: CSV + JSON для всех выбранных entity.

## AC-6. Dashboard

- `GET /workspaces/:wsid/dashboards/overview` возвращает агрегаты, которые сходятся с raw-записями (по количеству deals).
- Funnel: сумма по этапам == общему количеству open deals.
- Managers: каждый manager виден с deals_open/won/tasks_overdue.

## AC-7. Billing (mock)

- `POST /workspaces/:wsid/billing/deposits` в mock-режиме — сразу пишется `billing_ledger.kind='deposit'`.
- Баланс `billing_accounts.balance_cents` пересчитывается job'ом `recalc_balance`.
- Нет возможности открыть real payment URL в mock.

## AC-8. Jobs

- `GET /workspaces/:wsid/jobs/:id` возвращает актуальный `status`.
- `POST /.../jobs/:id/cancel` для `queued` → `cancelled`, для `running` — пытается прервать graceful.
- При падении job'а — `status=failed`, `error` заполнено.

## AC-9. Notifications

- После успешного sync — появляется notification `sync_complete`.
- После export ready — `export_ready` с ссылкой.
- `POST /notifications/:id/read` — `read_at` != NULL.

## AC-10. AI (mock)

- `POST /workspaces/:wsid/ai/analysis-jobs` с `kind=call_transcript, input_ref={call_id}` — выполняется через mock LLM, создаётся `ai_conversation_scores`.
- При consent=accepted и sample_size>=10 → паттерн появляется в `ai_research_patterns` с industry.
- При consent=revoked — `ai_research_patterns` не пишется.
- Анонимизация: в сохранённых полях нет PII (regex-проверка).

## AC-11. Admin

- Bootstrap-админ существует после первого запуска (`seed_admin.py`).
- `POST /admin/auth/login` работает, возвращает JWT со `scope=admin`.
- `GET /admin/workspaces` — видны все, без tenant-содержимого.
- Support-mode: start с `reason` → доступ к tenant-endpoints; каждый запрос → строка в `admin_audit_logs`.
- Support-mode без `reason` → 400.
- `POST /admin/billing/.../adjust` без `reason` → 400.

## AC-12. Retention

- Job `retention_warning_daily` вручную → юзер с отключённым 60 дней назад connection получает notification.
- Job `retention_delete_daily` вручную → tenant schema для connection 90+ дней DROPPED.

## AC-13. Security (cross-cutting)

- Токены CRM в БД — BYTEA, Fernet-encrypted, не строка.
- `GET /crm/connections/:id` в JSON-ответе не содержит ключей `access_token*`, `refresh_token*`.
- Логи api — нет строк с `Bearer <реальный токен>`; есть `Bearer ***`.
- Rate-limit срабатывает согласно `security/AUTH.md`.
- `admin_audit_logs` — записи есть для каждого админ-действия.

## AC-14. i18n

- Переключатель RU/EN работает.
- Все строки UI — через `next-intl`, нет хардкода.
- Backend error `code` не локализуется, но `message` может быть.
