# API Contract — Code9 Analytics

Base path: **`/api/v1`**. Формат — JSON, `Content-Type: application/json`.

## Стандартный формат ошибки

```json
{
  "error": {
    "code": "validation_error",
    "message": "Краткое описание",
    "field_errors": {
      "email": "must be a valid email"
    }
  }
}
```

- `code` — машинный строковой код (kebab-case или snake_case). Примеры:
  `validation_error`, `unauthorized`, `forbidden`, `not_found`, `rate_limited`,
  `conflict`, `invalid_credentials`, `email_not_verified`, `code_expired`,
  `too_many_attempts`, `internal_error`, `mock_only`.
- `field_errors` — необязательно, только для формальной валидации.

## Auth типы

- `public` — без токена.
- `user-jwt` — заголовок `Authorization: Bearer <access>`; scope=`user`.
- `admin-jwt` — заголовок `Authorization: Bearer <access>`; scope=`admin`; подпись — `ADMIN_JWT_SECRET`.

Refresh — httpOnly secure cookie `code9_refresh` (подробнее: `security/AUTH.md`).

---

# 1. Auth (public / user-jwt)

## POST `/auth/register`
Auth: **public**. Rate-limit: 3/min per IP.
Request:
```json
{ "email": "a@b.com", "password": "***", "locale": "ru" }
```
Response 201:
```json
{ "user_id": "uuid", "email_verification_required": true }
```
Errors: `validation_error`, `conflict` (email занят), `rate_limited`.

## POST `/auth/login`
Auth: **public**. Rate-limit: 5/min per IP + 10/min per email.
Request:
```json
{ "email": "a@b.com", "password": "***" }
```
Response 200:
```json
{
  "access_token": "jwt",
  "access_token_expires_in": 900,
  "user": { "id": "uuid", "email": "...", "display_name": null, "locale": "ru", "email_verified": true }
}
```
Cookie: `code9_refresh` (httpOnly, secure, SameSite=Lax, 30d).
Errors: `invalid_credentials`, `email_not_verified`, `rate_limited`.

## POST `/auth/logout`
Auth: **user-jwt**. Revokes refresh token.
Response 204.

## POST `/auth/refresh`
Auth: **public** (использует cookie `code9_refresh`).
Response 200: `{ "access_token": "jwt", "access_token_expires_in": 900 }`.
Errors: `unauthorized`.

## POST `/auth/verify-email/request`
Auth: **user-jwt**. Rate-limit: 3/10min per user.
Response 204. В dev — код пишется в лог api.

## POST `/auth/verify-email/confirm`
Auth: **user-jwt**. Rate-limit: 10/hour per user.
Request: `{ "code": "123456" }`.
Response 200: `{ "email_verified": true }`.
Errors: `code_expired`, `too_many_attempts`, `validation_error`.

## POST `/auth/password-reset/request`
Auth: **public**. Rate-limit: 3/10min per email.
Request: `{ "email": "a@b.com" }`.
Response 204 (всегда, чтобы не палить существование email).

## POST `/auth/password-reset/confirm`
Auth: **public**.
Request: `{ "email": "a@b.com", "code": "123456", "new_password": "***" }`.
Response 200: `{ "ok": true }`. Побочно: все refresh-токены юзера revoke.
Errors: `code_expired`, `too_many_attempts`, `validation_error`.

## GET `/auth/me`
Auth: **user-jwt**. Response 200:
```json
{
  "id": "uuid",
  "email": "...",
  "display_name": null,
  "locale": "ru",
  "email_verified": true,
  "two_factor_enabled": false,
  "workspaces": [{ "id": "uuid", "name": "...", "role": "owner" }]
}
```

---

# 2. Workspaces

## GET `/workspaces`
Auth: **user-jwt**. Response 200: массив объектов workspace (id, name, slug, role текущего пользователя).

## POST `/workspaces`
Auth: **user-jwt**.
Request: `{ "name": "Acme", "slug": "acme", "locale": "ru", "industry": "b2b_saas" }`.
Response 201: объект workspace.

## GET `/workspaces/:id`
Auth: **user-jwt** + членство.
Response 200: detailed workspace.

## PATCH `/workspaces/:id`
Auth: **user-jwt**, роль `owner` или `admin`.
Request: частичный объект.
Response 200.

## GET `/workspaces/:id/members`
Auth: **user-jwt** + членство.
Response 200: массив members (включая pending-приглашения).

## POST `/workspaces/:id/members/invite`
Auth: **user-jwt**, роль `owner|admin`.
Request: `{ "email": "...", "role": "analyst" }`.
Response 201.

## DELETE `/workspaces/:id/members/:member_id`
Auth: **user-jwt**, роль `owner|admin`. Response 204.

---

# 3. CRM Connections

## GET `/workspaces/:wsid/crm/connections`
Auth: **user-jwt** + членство.
Response 200: массив. Токены НИКОГДА не возвращаются.
```json
[{
  "id": "uuid",
  "provider": "amocrm",
  "status": "active",
  "external_account_id": "12345",
  "external_domain": "mycompany.amocrm.ru",
  "last_sync_at": "2026-04-18T10:00:00Z",
  "token_expires_at": "2026-04-25T10:00:00Z"
}]
```

## POST `/workspaces/:wsid/crm/connections`
Auth: **user-jwt**, роль `owner|admin`.
Request: `{ "provider": "amocrm" }`.
Response 201:
```json
{ "id": "uuid", "status": "pending", "oauth_authorize_url": "/api/v1/crm/oauth/amocrm/start?connection_id=..." }
```
В `MOCK_CRM_MODE=true` — возвращается `mock_complete_url` вместо OAuth.

## GET `/crm/oauth/amocrm/start`
Auth: **user-jwt** (через state param).
Query: `connection_id`.
Response: 302 → authorize URL amoCRM (в mock — сразу на `/crm/oauth/amocrm/callback`).

## GET `/crm/oauth/amocrm/callback`
Auth: **public** (защищено через `state`).
Query: `code`, `state`, `referer`.
Response: 302 → web app с flash-сообщением. Сайд-эффекты: `crm_connections.status=active`, enqueue `bootstrap_tenant_schema`.

## POST `/crm/connections/:id/reconnect`
Auth: **user-jwt**, роль `owner|admin`. Возвращает новый `oauth_authorize_url`.

## POST `/crm/connections/:id/pause`
Auth: **user-jwt**, роль `owner|admin`. Status → `paused`.

## POST `/crm/connections/:id/resume`
Auth: **user-jwt**, роль `owner|admin`. Status → `active`.

## POST `/crm/connections/:id/delete/request`
Auth: **user-jwt**, роль `owner`. Создаёт `deletion_requests`, шлёт email-код. Response 202:
```json
{ "deletion_request_id": "uuid", "expires_at": "..." }
```

## POST `/crm/connections/:id/delete/confirm`
Auth: **user-jwt**, роль `owner`.
Request: `{ "code": "123456" }`.
Response 202: `{ "job_id": "uuid" }`.
Errors: `code_expired`, `too_many_attempts`.

## POST `/crm/connections/:id/sync`
Auth: **user-jwt**. Enqueues `fetch_crm_data`. Response 202: `{ "job_id": "uuid" }`.

---

# 4. Audit

## POST `/workspaces/:wsid/audit/reports`
Auth: **user-jwt**. Enqueues `run_audit_report`.
Request: `{ "crm_connection_id": "uuid", "period": "last_90_days" }`.
Response 202: `{ "job_id": "uuid" }`.

## GET `/workspaces/:wsid/audit/reports`
Auth: **user-jwt**. Response 200: массив отчётов (id, created_at, summary).

## GET `/workspaces/:wsid/audit/reports/:id`
Auth: **user-jwt**. Response 200: полный отчёт (JSON).

---

# 5. Export

## POST `/workspaces/:wsid/export/jobs`
Auth: **user-jwt**, роль `owner|admin`.
Request: `{ "crm_connection_id": "uuid", "format": "zip_csv_json", "entities": ["deals","contacts","tasks"] }`.
Response 202: `{ "job_id": "uuid" }`.

## GET `/workspaces/:wsid/export/jobs/:id`
Auth: **user-jwt**. Response 200: `{ "id","status","download_url?","download_url_expires_at?" }`.

---

# 6. Dashboards

## GET `/workspaces/:wsid/dashboards/overview`
Auth: **user-jwt**. Query: `crm_connection_id`, `period`.
Response 200: агрегаты (funnel, conversions, managers_activity, abandoned_deals).

## GET `/workspaces/:wsid/dashboards/funnel`
Auth: **user-jwt**. Response 200: массив `{ stage, count, conversion_from_previous }`.

## GET `/workspaces/:wsid/dashboards/managers`
Auth: **user-jwt**. Response 200: массив `{ user_id, deals_open, deals_won, tasks_overdue }`.

---

# 7. Billing

## GET `/workspaces/:wsid/billing/account`
Auth: **user-jwt**. Response 200: `{ balance_cents, currency, plan, provider }`.

## GET `/workspaces/:wsid/billing/ledger`
Auth: **user-jwt**. Query: `limit`, `cursor`. Response 200: cursor-пагинация.

## POST `/workspaces/:wsid/billing/deposits`
Auth: **user-jwt**, роль `owner`.
Request: `{ "amount_cents": 100000, "currency": "RUB", "provider": "yookassa" }`.
Response 201: `{ "redirect_url": "...", "payment_id": "..." }` (в mock — сразу `kind=deposit` в ledger).

## POST `/billing/webhooks/yookassa`
Auth: **public** (подпись по `YOOKASSA_WEBHOOK_SECRET`).
Response 200.

## POST `/billing/webhooks/stripe`
Auth: **public** (подпись по `STRIPE_WEBHOOK_SECRET`).
Response 200.

---

# 8. Jobs

## GET `/workspaces/:wsid/jobs/:id`
Auth: **user-jwt**. Response 200: `{ id, kind, status, payload, result?, error?, started_at, finished_at }`.

## POST `/workspaces/:wsid/jobs/:id/cancel`
Auth: **user-jwt**. Response 202.

---

# 9. Notifications

## GET `/workspaces/:wsid/notifications`
Auth: **user-jwt**. Query: `only_unread=true`.
Response 200: массив.

## POST `/workspaces/:wsid/notifications/:id/read`
Auth: **user-jwt**. Response 204.

---

# 10. AI

## GET `/workspaces/:wsid/ai/consent`
Auth: **user-jwt**. Response 200: `{ status, accepted_at?, revoked_at?, terms_version? }`.

## POST `/workspaces/:wsid/ai/consent`
Auth: **user-jwt**, роль `owner`.
Request: `{ "action": "accept" | "revoke", "terms_version": "v1" }`.
Response 200.

## POST `/workspaces/:wsid/ai/analysis-jobs`
Auth: **user-jwt**.
Request: `{ "kind": "call_transcript", "input_ref": { "call_id": "uuid" } }`.
Response 202: `{ "job_id": "uuid" }`.

## GET `/workspaces/:wsid/ai/analysis-jobs/:id`
Auth: **user-jwt**. Response 200: полный job + ссылка на score (если завершён).

## GET `/workspaces/:wsid/ai/scores/:score_id`
Auth: **user-jwt**. Response 200: `ai_conversation_scores` row.

## GET `/workspaces/:wsid/ai/patterns`
Auth: **user-jwt**. Response 200: массив `ai_behavior_patterns`.

## GET `/workspaces/:wsid/ai/knowledge`
Auth: **user-jwt**. Response 200: массив `ai_client_knowledge_items`.

## POST `/workspaces/:wsid/ai/knowledge`
Auth: **user-jwt**, роль `owner|admin`.
Request: `{ "source": "manual", "title": "...", "body": "..." }`.
Response 201.

---

# 11. Admin (admin-jwt, префикс `/admin`)

## POST `/admin/auth/login`
Auth: **public**. Rate-limit: 5/min per IP.
Request: `{ "email": "...", "password": "..." }`.
Response 200: `{ "access_token": "jwt", "access_token_expires_in": 900, "admin": { "id","email","role" } }`.

## POST `/admin/auth/logout`
Auth: **admin-jwt**. Response 204.

## GET `/admin/workspaces`
Auth: **admin-jwt**. Query: `q`, `status`, `page`. Response 200: paginated workspaces (без tenant-данных).

## GET `/admin/workspaces/:id`
Auth: **admin-jwt**. Response 200: workspace + list connections + billing summary.

## POST `/admin/workspaces/:id/pause`
Auth: **admin-jwt**. Логируется.

## POST `/admin/workspaces/:id/resume`
Auth: **admin-jwt**. Логируется.

## POST `/admin/connections/:id/pause`
Auth: **admin-jwt**.

## POST `/admin/connections/:id/resume`
Auth: **admin-jwt**.

## POST `/admin/jobs/:id/restart`
Auth: **admin-jwt**.

## POST `/admin/billing/:workspace_id/adjust`
Auth: **admin-jwt**, role=`superadmin|support`.
Request: `{ "amount_cents": -10000, "reason": "refund for outage" }`.
Response 200.

## POST `/admin/support-mode/start`
Auth: **admin-jwt**.
Request: `{ "workspace_id": "uuid", "reason": "ticket #123" }`.
Response 200: `{ "support_session_id": "uuid", "expires_at": "..." }` (макс 60 мин).

## POST `/admin/support-mode/end`
Auth: **admin-jwt**. Response 204.

## GET `/admin/support-mode/session/:id/tenant/deals`
Auth: **admin-jwt** + активный support-session.
Response 200: read-only список deals из tenant. Каждый запрос — строка в `admin_audit_logs`.

## GET `/admin/audit-logs`
Auth: **admin-jwt**. Query: `admin_user_id`, `action`, `from`, `to`. Response 200: paginated.

## GET `/admin/ai/research-patterns`
Auth: **admin-jwt**.
Response 200: агрегированные `ai_research_patterns` (де-идентифицированные).

---

# 12. Meta

## GET `/`
Auth: **public**. Response 200: `{ "service":"code9-api","env":"development","version":"0.1.0" }`.

## GET `/health`
Auth: **public**. Response 200: `{ "status":"ok" }`.

## GET `/api/v1/health`
Auth: **public**. Response 200: `{ "status":"ok", "db":"ok", "redis":"ok" }` (проверяет зависимости).
