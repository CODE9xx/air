# Retention Policy — Code9 Analytics

## Зачем

1. Минимизация хранения PII (152-ФЗ, GDPR).
2. Удаление отключённых клиентов, не платящих подписку.
3. Снижение затрат на storage.

## Календарь

| День после отключения / события | Действие |
|---|---|
| **0** | Момент отключения CRM (status=deleted / deletion_request completed) или прекращения активности workspace. |
| **1** | Финальный snapshot в ledger; метрики пересчитаны. |
| **7** | Уведомление в UI: «данные будут удалены через 83 дня». |
| **30** | `retention_read_only` job: workspace/connection переходит в read-only (нельзя запускать новые sync/export/AI). |
| **60** | `retention_warning` job: email + in-app уведомление «до удаления 30 дней». |
| **75** | `retention_warning` job: email «до удаления 15 дней». |
| **85** | `retention_warning` job: email «до удаления 5 дней». |
| **90** | `retention_delete` job: финальное удаление (см. ниже). |

## Что именно удаляется на день 90

- **Tenant schema** `crm_<provider>_<shortid>` — `DROP SCHEMA ... CASCADE` (все raw_*, normalized, knowledge_base).
- `public.crm_connections` — обнуляем токены, оставляем row (нужна для audit/ledger) со `status='deleted'`.
- `public.ai_analysis_jobs` / `ai_conversation_scores` — удаляются полностью (с FK cascade).
- `public.ai_client_knowledge_items` — удаляются.
- `public.jobs` связанные — `crm_connection_id=NULL` (SET NULL).

## Что СОХРАНЯЕТСЯ

- `public.billing_ledger` — финансовая история (для бухгалтерии).
- `public.admin_audit_logs` — полностью сохраняется навсегда.
- `public.workspaces` row со `status='deleted'` (если workspace удалён целиком).
- `public.users` — не удаляется автоматически (у юзера могут быть другие workspaces). Отдельная процедура «удалить аккаунт» по GDPR-запросу.
- `ai_research_patterns` — полностью анонимны, сохраняются навсегда.

## Реализация jobs (rq-scheduler, Wave 2)

| Job | Расписание | Что делает |
|---|---|---|
| `retention_warning_daily` | каждый день 03:00 UTC | находит connections/workspaces на днях 7/60/75/85, шлёт уведомления |
| `retention_read_only_daily` | каждый день 03:15 UTC | переводит в read-only на дне 30 |
| `retention_delete_daily` | каждый день 04:00 UTC | финальное удаление на дне 90 |

Все три — в очереди `retention`.

## Trigger от удаления подключения

- После `POST /crm/connections/:id/delete/confirm` → немедленно `delete_connection_data` job (обход retention-календаря).
- Это добровольное удаление по запросу клиента, не ждём 90 дней.

## Workspace-level retention

- Если workspace неактивен 365 дней (последний login owner'а) + нет активных платных подписок → email «удалим workspace через 30 дней, если не подтвердишь».
- Не подтвердили → workspace.status='deleted', tenant-схемы удаляются (если ещё не были).
- Правила детализируются в V1.

## GDPR / 152-ФЗ «Забудьте меня»

- Endpoint `POST /auth/account/delete-request` **(V1, не MVP)** — запускает flow удаления аккаунта user + всех связанных workspaces, где он owner.
- Срок обработки: 30 дней.

## Dev-режим

- Retention-jobs можно запустить вручную через `make worker-shell`:
  ```
  python -c "from worker.retention import retention_delete_daily; retention_delete_daily()"
  ```
- В `APP_ENV=development` — календарь ускоряется (по flag `RETENTION_DEV_SPEEDUP=1`, V2).
