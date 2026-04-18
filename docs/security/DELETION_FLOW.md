# Deletion Flow — Code9 Analytics

Удаление CRM-подключения — необратимое действие. Защищено email-кодом.

## Состояния `crm_connections.status` в жизненном цикле удаления

```
active / paused / lost_token
        │
        │  user нажал "Удалить подключение"
        ▼
    (POST /crm/connections/:id/delete/request)
    + создаётся deletion_requests (awaiting_code)
    + отправляется email с 6-значным кодом
        │
        │  user ввёл код
        ▼
    (POST /crm/connections/:id/delete/confirm)
    + deletion_requests.status = confirmed
    + enqueue delete_connection_data job
        │
        ▼
     status = deleting
        │
        │  worker: DROP SCHEMA <tenant> CASCADE
        ▼
     status = deleted  (tenant_schema = NULL, токены обнулены)
```

## Шаги API

### 1. `POST /crm/connections/:id/delete/request`
- Auth: **user-jwt**, роль `owner` в workspace.
- Проверяет, что нет активной `deletion_requests` с `status='awaiting_code'`.
- Создаёт row:
  - `email_code_hash = argon2id("123456")`
  - `expires_at = NOW() + 10 minutes`
  - `max_attempts = 5`
- Отправляет email пользователю. В dev — пишет в stdout `[DEV EMAIL] code=123456`.
- Response 202: `{ "deletion_request_id": "uuid", "expires_at": "..." }`.

### 2. `POST /crm/connections/:id/delete/confirm`
- Auth: **user-jwt**, роль `owner`.
- Request: `{ "code": "123456" }`.
- Находит последнюю `deletion_requests` для этого `crm_connection_id` в `awaiting_code`.
- `attempts += 1`. Если > `max_attempts` → `status='cancelled'`, ошибка `too_many_attempts`.
- Если `expires_at < NOW()` → `status='expired'`, ошибка `code_expired`.
- Если `argon2.verify(email_code_hash, code)` → `status='confirmed'`, `confirmed_at=NOW()`.
- Enqueue `delete_connection_data` job в очередь `retention` с `connection_id`.
- Response 202: `{ "job_id": "uuid" }`.

## Job `delete_connection_data`

```
1. SELECT tenant_schema FROM crm_connections WHERE id=? FOR UPDATE
2. UPDATE crm_connections SET status='deleting' WHERE id=?
3. IF tenant_schema IS NOT NULL:
     EXECUTE 'DROP SCHEMA "' || tenant_schema || '" CASCADE'
4. UPDATE crm_connections
     SET status='deleted',
         tenant_schema=NULL,
         access_token_encrypted=NULL,
         refresh_token_encrypted=NULL,
         deleted_at=NOW()
     WHERE id=?
5. UPDATE deletion_requests SET status='completed', completed_at=NOW() WHERE id=?
6. INSERT INTO notifications (kind='connection_deleted', ...)
```

Всё внутри одной транзакции, кроме шага 3 (DROP SCHEMA — отдельной транзакцией, так как DDL).

## Что сохраняется после удаления

- `public.crm_connections` row — **остаётся** (status=deleted), нужна для ledger и audit.
- `public.billing_ledger` — **сохраняется** (финансовая история).
- `public.admin_audit_logs` — **сохраняется**.
- `public.jobs` связанные — `crm_connection_id=NULL` (SET NULL).
- `public.notifications` — **сохраняются** для пользователя.

## Что удаляется

- Вся tenant schema `crm_<...>` целиком (все raw_*, normalized, knowledge_base).
- `access_token_encrypted` / `refresh_token_encrypted` обнуляются.

## Нельзя реактивировать

- После `status='deleted'` реактивация запрещена.
- Если клиент хочет вернуться — создаёт **новое** подключение (новая schema, новый shortid).

## Ошибки

| Ситуация | code |
|---|---|
| Код истёк | `code_expired` |
| >5 попыток | `too_many_attempts` |
| Нет активной deletion_request | `not_found` |
| Подключение уже удалено | `conflict` |
| Не owner | `forbidden` |

## Dev-режим

- `DEV_EMAIL_MODE=log` → код пишется в stdout api-контейнера.
- Для тестов QA — это достаточно.

## Тестовые сценарии (для QA)

1. Owner запрашивает delete → получает код в логе → вводит правильный → через ≤30s status=deleted, schema dropped.
2. Owner вводит неверный код 5 раз → 6-й запрос `too_many_attempts`, status=cancelled.
3. Owner не подтверждает за 10 мин → `expires_at` проходит → `code_expired`.
4. Не-owner пытается → 403 forbidden.
5. Повторная delete/request на уже `deleted` → 409 conflict.
