# apps/worker — Code9 RQ worker

**Owner:** DB & Worker Engineer.

RQ 1.16 + Redis. Один процесс слушает 6 бизнес-очередей + `default`.
Все долгие операции (CRM sync, AI, экспорт, retention, billing) бегут здесь.

## Очереди

| Queue | Примеры jobs | Concurrency MVP |
|---|---|---|
| `crm` | `bootstrap_tenant_schema`, `fetch_crm_data`, `refresh_token`, `normalize_tenant_data` | 2 |
| `export` | `trial_export`, `full_export`, `build_export_zip` | 2 |
| `audit` | `run_audit_report` (mock 12 450 deals и т.д.) | 1 |
| `ai` | `analyze_conversation`, `extract_patterns`, `anonymize_patterns`, `update_research_dataset` | 1 |
| `retention` | `retention_warning`, `retention_read_only`, `retention_delete`, `delete_connection_data` | 1 |
| `billing` | `recalc_balance`, `billing_monthly_charge`, `billing_usage_charge`, `issue_invoice` | 1 |

Имена и `JobKind` синхронизированы с `apps/api/app/db/models/enums.py` →
`docs/db/SCHEMA.md` §1.9.

## Запуск

```bash
docker compose up worker
docker compose logs -f worker
```

Параметры env:
- `WORKER_QUEUES` — список очередей через запятую (default: все).
- `WORKER_NAME` — имя (для логов RQ).
- `REDIS_URL` — `redis://redis:6379/0` по умолчанию.
- `MOCK_CRM_MODE=true` — обязателен в MVP (никаких реальных HTTP).

## Graceful shutdown

RQ ловит `SIGTERM`/`SIGINT`: после завершения текущего job worker гасится.

## Scheduler (retention)

`worker/scheduler.py` — даёт два режима:

1. **rq-scheduler** (опц., V1): cron-задачи `retention_warning_daily` (03:00 UTC),
   `retention_read_only_daily` (03:15 UTC), `retention_delete_daily` (04:00 UTC).
   Требует `pip install rq-scheduler` + отдельный процесс
   `python -m worker.scheduler`.
2. **MVP-loop** (по умолчанию): отдельный сервис в docker-compose **не добавлен** —
   в MVP retention запускается вручную из `worker-shell`:
   ```bash
   docker compose exec worker python -c \
     "from worker.scheduler import retention_warning_daily; retention_warning_daily()"
   ```

**TODO (V1):** добавить service `worker-scheduler` в `docker-compose.yml`
после стабилизации календаря retention.

## Tenant-schema lifecycle

1. BE при активации connection enqueue'ит `bootstrap_tenant_schema(connection_id)`.
2. Worker:
   - генерит `crm_<provider>_<shortid>` (см. `worker/lib/tenant.py`);
   - вызывает `apply_tenant_migrations(schema)` (alembic tenant env через
     `scripts/migrations/apply_tenant_template.py`);
   - проставляет `crm_connections.tenant_schema` и переводит status в `active`.
3. При удалении — `delete_connection_data` делает
   `DROP SCHEMA "<name>" CASCADE` + чистит токены.

## Безопасность

- Токены CRM шифруются Fernet (`worker/lib/crypto.py`, ключ `FERNET_KEY`).
- Лог-маска (`worker/lib/log_mask.py`) глушит `access_token`/`refresh_token`/
  `Bearer <…>` в любых выводах.
- Имена tenant-схем валидируются regex'ом перед интерполяцией в DDL.

## Локальный dev цикл

```bash
# 1. поднять стек
docker compose up postgres redis api worker

# 2. main миграции
docker compose exec api alembic \
    -c /app/app/db/migrations/alembic.ini --name main upgrade head

# 3. bootstrap admin + demo workspace
docker compose exec api python /app/scripts/seed/seed_admin.py
docker compose exec api python /app/scripts/seed/seed_demo_workspace.py

# 4. убедиться, что worker подобрал очереди
docker compose logs --tail=20 worker
```
