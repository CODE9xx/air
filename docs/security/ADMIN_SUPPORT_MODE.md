# Admin & Support Mode — Code9 Analytics

## Принципы

1. **Админы — отдельная сущность.** Таблица `admin_users`, отдельный JWT secret (`ADMIN_JWT_SECRET`), отдельный login endpoint.
2. **Без прямого доступа к tenant-данным.** Администратор по умолчанию **не видит** содержимое tenant-схем. Только метаданные: workspaces, connections, jobs, billing.
3. **Support Mode** — явная сессия с `reason`, ограниченная временем, каждый запрос логируется.
4. **Full audit trail.** Каждое действие администратора пишется в `admin_audit_logs` **в той же транзакции**, что и действие (см. ADR-008).

## `admin_users.role`

| Роль | Что может |
|---|---|
| `superadmin` | всё: pause/resume, restart jobs, billing adjust, support-mode, user impersonation (V1), инвайты админов |
| `support` | pause/resume connection, restart job, начать support-mode, видеть billing (read-only) |
| `analyst` | видеть дашборды админки + ai_research_patterns (anonymous), НЕ может ничего менять |

## Без support-mode — что доступно

- `GET /admin/workspaces` — список всех workspaces (id, name, owner_email_masked, status, created_at).
- `GET /admin/workspaces/:id` — workspace + список connections + billing-summary. **Без** содержимого tenant.
- `GET /admin/audit-logs` — все admin-логи.
- `POST /admin/*/pause|resume` — pause/resume workspace/connection.
- `POST /admin/jobs/:id/restart` — рестарт job'а.
- `POST /admin/billing/:workspace_id/adjust` — ручная корректировка баланса с обязательным `reason`.
- `GET /admin/ai/research-patterns` — анонимизированные паттерны (без workspace-id).

## Support Mode

### Зачем
Иногда нужен read-доступ к tenant-данным клиента (отладка, поддержка). Этот доступ **не даётся по умолчанию**.

### Запуск
```
POST /admin/support-mode/start
{ "workspace_id": "uuid", "reason": "ticket #123, клиент просит проверить" }
```
- Создаётся `admin_support_sessions` **(таблицу добавит DW в Wave 2)** с полями:
  `id, admin_user_id, workspace_id, reason, expires_at (NOW()+60min), ended_at`.
- Возвращается `support_session_id`.
- **Синхронно** пишется в `admin_audit_logs`:
  `action='support_mode_start', target_type='workspace', target_id=workspace_id, metadata={reason,session_id}`.

### Доступ к tenant-данным
- Только через endpoint'ы `/admin/support-mode/session/:id/tenant/*`, которые проверяют:
  - session не `ended_at`;
  - `expires_at > NOW()`;
  - `workspace_id` session == запрашиваемый.
- Каждый запрос к tenant-ресурсу = новая строка в `admin_audit_logs`:
  `action='support_mode_read_tenant', target_type='connection'|'deal'|'contact'|..., metadata={session_id, endpoint, params}`.
- Данные возвращаются **read-only**, без PII-полей, которые не нужны для отладки (`phone` → `phone_primary_hash` уже хранится, а в раw.payload — маскируется по regex).

### Завершение
- Автоматически: через 60 минут (`expires_at`).
- Вручную: `POST /admin/support-mode/end`.
- Любая попытка использовать session после `ended_at` → 403, пишется `action='support_mode_expired_access_attempt'`.

## Ограничения

- Админ **не** получает OAuth-токены клиента даже в support-mode.
- Админ **не** получает расшифрованный `raw.payload.phone` напрямую — только уже обработанные поля (`phone_primary_hash`).
- Админ **не** может править данные в tenant.
- `billing_adjustment` — требует обязательного `reason` (не пустого). Без `reason` — 400.

## Логирование

- `admin_audit_logs` пишется **в той же транзакции**, что и действие. Если INSERT в логи упал — действие откатывается.
- Поля: `admin_user_id, action, target_type, target_id, metadata (jsonb), ip, user_agent, created_at`.

## Bootstrap-админ

- При первом запуске — seed-скрипт `seed_admin.py` (DW Wave 2) создаёт `admin_users` row с ролью `superadmin` по `ADMIN_BOOTSTRAP_EMAIL` / `ADMIN_BOOTSTRAP_PASSWORD`.
- Если админы уже есть — seed пропускается.
- В prod — пароль должен быть сменён после первого логина (V1: принудительная смена).

## Rate-limits и защита

- `/admin/auth/login`: 5/min per IP.
- Неудачные попытки login админа → notifications сырым email'ом (V1).
- Подозрительные паттерны (много support-mode с разными workspaces за короткое время) → alert (V1).
