"""
Alembic env для tenant-schema template.

Требования:
- Имя целевой схемы приходит как ``-x schema=<name>`` (обязательно).
- ВСЕ DDL создаются внутри этой схемы: в начале транзакции делаем
  ``SET LOCAL search_path = "<schema>", public``; autogenerate использует
  ``include_schemas=False`` + ``version_table_schema=<schema>``.
- Версионная таблица — внутри tenant-схемы (у каждой своя история миграций).
"""
from __future__ import annotations

import os
import re
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool, text

_REPO_ROOT = Path(__file__).resolve().parents[5]
_API_ROOT = _REPO_ROOT / "apps" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.db.models import TenantBase  # noqa: E402
from app.db import models  # noqa: E402,F401 — регистрирует tenant-модели

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

_SCHEMA_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _get_url() -> str:
    url = os.getenv("DATABASE_URL", "postgresql://code9:code9@postgres:5432/code9")
    return (
        url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        .replace("postgres+asyncpg://", "postgresql+psycopg2://")
    )


def _get_schema() -> str:
    """
    Читаем имя tenant-схемы из ``-x schema=<name>``.

    Валидация имени — обязательна: оно вставляется в DDL как идентификатор
    (квотируем, но всё же). Разрешаем только ``[a-z_][a-z0-9_]{0,62}``.
    """
    x_args = context.get_x_argument(as_dictionary=True)
    schema = x_args.get("schema")
    if not schema:
        raise RuntimeError(
            "tenant env: требуется -x schema=<schema_name>; "
            "например: alembic --name tenant -x schema=crm_amo_abc12345 upgrade head"
        )
    if not _SCHEMA_NAME_RE.fullmatch(schema):
        raise RuntimeError(f"tenant env: невалидное имя схемы {schema!r}")
    return schema


target_metadata = TenantBase.metadata


def run_migrations_offline() -> None:
    schema = _get_schema()
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="alembic_version",
        version_table_schema=schema,
        include_schemas=False,
    )
    with context.begin_transaction():
        # В offline режим просто пишем оператор, alembic его не исполнит сам.
        context.execute(f'SET search_path = "{schema}", public')
        context.run_migrations()


def run_migrations_online() -> None:
    schema = _get_schema()
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Локальный search_path на время транзакции миграции.
        connection.execute(text(f'SET LOCAL search_path = "{schema}", public'))
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            version_table="alembic_version",
            version_table_schema=schema,
            # Таблицы TenantBase без ``schema=...`` — ``include_schemas`` не нужен.
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
