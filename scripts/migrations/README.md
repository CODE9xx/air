# scripts/migrations

Хелперы поверх alembic для multi-schema миграций Code9 Analytics.

**Owner:** DB & Worker Engineer.

## Архитектура

Два независимых alembic environment'а
(см. `apps/api/app/db/migrations/alembic.ini`):

| Секция | Path | Что делает |
|---|---|---|
| `[main]` | `apps/api/app/db/migrations/main/` | DDL для `public` schema (users, workspaces, …) |
| `[tenant]` | `apps/api/app/db/migrations/tenant/` | DDL шаблона tenant-схемы (`raw_*`, `deals`, …) |

`tenant` env требует `-x schema=<name>` в каждом вызове и кладёт
`alembic_version` **внутри** tenant-схемы.

## Скрипты

### `apply_tenant_template.py`

Главный helper: `CREATE SCHEMA IF NOT EXISTS "<name>"` + `alembic upgrade head`
для tenant env.

```bash
python -m scripts.migrations.apply_tenant_template crm_amo_abc12345
```

Используется:
- worker job'ом `bootstrap_tenant_schema` (через `apps/worker/worker/lib/tenant.py`);
- CI/локально вручную;
- ре-применением шаблона ко всем активным tenant-схемам после мержа новой
  миграции.

### `apply_tenant_ddl.py`

CLI-обёртка с тем же эффектом + поддержка `--drop`.

```bash
python -m scripts.migrations.apply_tenant_ddl crm_amo_abc12345
python -m scripts.migrations.apply_tenant_ddl crm_amo_abc12345 --drop
```

## ADR — почему alembic, а не один `tenant_ddl.sql`

В Brief 3 допускался простой путь: один SQL-файл + `format('%I', schema)`.
Мы выбрали полноценный alembic-путь, т.к.:

1. ORM-модели уже написаны BE (см. `apps/api/app/db/models/tenant_schema.py`),
   и `MainBase.metadata.create_all` / `TenantBase.metadata.create_all` гарантируют
   схему, идентичную ORM (избегаем дрифта DDL ↔ ORM).
2. Alembic ведёт `alembic_version` внутри каждой tenant-схемы — это
   понадобится для апгрейдов шаблона в V1.
3. Ре-использование одного и того же `env.py` из CI, CLI и worker-job'а.

Цена: одна дополнительная зависимость (`alembic` в `apps/worker/pyproject.toml`).

## Полный жизненный цикл tenant-схемы

| Событие | Действие |
|---|---|
| `crm_connections.status -> active` | enqueue `bootstrap_tenant_schema` |
| Job `bootstrap_tenant_schema` | `apply_tenant_template(schema)` → апдейт `crm_connections.tenant_schema` |
| Новая tenant-миграция | CI прогоняет `apply_tenant_template` по всем active connections |
| `delete_connection_data` | `drop_tenant_schema(name)` (DROP SCHEMA … CASCADE) |
