# Migration Strategy — Code9 Analytics

## Инструмент
Alembic (sync, через psycopg2). Async-driver (asyncpg) — только для рантайма API/worker'а.

## Структура каталогов (целевая, Wave 2)

```
apps/api/app/db/
  models/
    main/                # модели для public.*
    tenant/              # модели для tenant-template
  migrations/
    main/                # alembic env для public.*
      env.py
      script.py.mako
      versions/
    tenant/              # alembic env для tenant-template
      env.py
      script.py.mako
      versions/
```

Два **отдельных** alembic environment'а:
- `main` — управляет схемой `public`.
- `tenant` — управляет шаблоном tenant-схем; параметр `--x-schema=<name>` указывает целевую схему.

## Правила для `main` миграций

- Всё в `public`.
- Никогда не ссылается FK на tenant-таблицы.
- Поля `tenant_schema` в `public.crm_connections` — просто TEXT, без FK.

## Правила для `tenant` миграций

- Все объекты создаются в schema, переданной через `--x-schema`.
- FK — только внутри схемы.
- Перед каждой миграцией: `SET search_path TO <schema>, public`.

## Жизненный цикл tenant-schema

| Событие | Действие |
|---|---|
| `crm_connections.status -> active` | enqueue `bootstrap_tenant_schema` job |
| Job `bootstrap_tenant_schema` | `CREATE SCHEMA crm_<provider>_<shortid>` → `apply tenant migrations head` → обновляет `crm_connections.tenant_schema` |
| Новая tenant-миграция мержится | CI прогоняет `apply_tenant_template.py` по всем активным схемам |
| `delete_connection_data` job | `DROP SCHEMA <name> CASCADE` → `crm_connections.tenant_schema = NULL` |

## Скрипты

- `scripts/migrations/create_tenant_schema.py <connection_id>` — обёртка над job'ом.
- `scripts/migrations/apply_tenant_template.py` — итерируется по всем `crm_connections WHERE status='active'` и применяет миграции.
- `scripts/migrations/drop_tenant_schema.py <schema_name>` — экстренный сброс.

## Naming conventions для миграций

- Файлы: `YYYYMMDDHHMM_<short_slug>.py`.
- Slug — kebab-case, ≤40 символов.
- Сообщение в `revision`: предложение, ≤72 символа, императив (например, `Add user_sessions table`).

## Транзакции

- Все DDL alembic-миграций — внутри `op.execute(...)` с явной транзакцией.
- DROP SCHEMA tenant — отдельной транзакцией (нельзя откатывать после удаления данных).

## Откат (downgrade)

- `main` — обязательно реализуем `downgrade()` для каждой миграции.
- `tenant` — `downgrade` опционально (для prod практически не используется).

## Multi-environment

- В CI: применяем `main upgrade head`, затем для каждой test-tenant — `tenant upgrade head`.
- В prod: миграции применяются init-job'ом перед стартом API.

## Backup

- Перед `delete_connection_data` job'ом — снэпшот в S3 (V1, не в MVP).
- В MVP — данные удаляются необратимо; пользователь предупреждён email-кодом.
