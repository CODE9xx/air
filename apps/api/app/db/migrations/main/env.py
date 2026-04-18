"""
Alembic env для main-schema (public).

- URL берём из ENV ``DATABASE_URL``. Для alembic'а конвертируем asyncpg → psycopg2.
- ``target_metadata = MainBase.metadata`` — все public-таблицы.
- ``version_table`` по умолчанию — ``alembic_version`` в public.
- sslmode: asyncpg принимает ``ssl=require``, libpq/psycopg2 ждёт
  ``sslmode=require``. При конвертации драйвера мы также транслируем
  query-параметры — иначе Timeweb managed Postgres (TLS-only) отобъёт alembic.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from alembic import context
from sqlalchemy import engine_from_config, pool

# Позволяем импортировать ``app.*`` при запуске alembic через
# ``alembic -c apps/api/app/db/migrations/alembic.ini --name main ...``
# вне api-контейнера (например, из корня repo).
_REPO_ROOT = Path(__file__).resolve().parents[5]
_API_ROOT = _REPO_ROOT / "apps" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

# Обязательно импортируем после настройки sys.path.
from app.db.models import MainBase  # noqa: E402
from app.db import models  # noqa: E402,F401 — регистрирует все модели в MainBase.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _translate_asyncpg_to_psycopg2(url: str) -> str:
    """
    Конвертирует asyncpg-URL в psycopg2-URL (sync-driver для alembic).

    Драйвер: ``postgresql+asyncpg://`` → ``postgresql+psycopg2://``
             ``postgres+asyncpg://``    → ``postgresql+psycopg2://``

    Query-параметры: asyncpg использует ``ssl=require`` (libpq-style
    ``sslmode=require`` он не понимает и падает). psycopg2 наоборот —
    читает ``sslmode``. Поэтому при смене драйвера транслируем и сам параметр.

    ``sslmode=...`` оставляем как есть (если кто-то уже положил libpq-стиль).
    """
    # 1. Схема/драйвер.
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql+psycopg2://" + url[len("postgresql+asyncpg://"):]
    elif url.startswith("postgres+asyncpg://"):
        url = "postgresql+psycopg2://" + url[len("postgres+asyncpg://"):]

    # 2. Query-params: ssl → sslmode.
    parts = urlsplit(url)
    if not parts.query:
        return url

    qs = parse_qsl(parts.query, keep_blank_values=True)
    translated: list[tuple[str, str]] = []
    for key, value in qs:
        if key == "ssl":
            # asyncpg → libpq mapping
            # true/True/require → require; disable/false → disable
            low = value.strip().lower()
            if low in ("true", "require", "1"):
                translated.append(("sslmode", "require"))
            elif low in ("false", "disable", "0", ""):
                translated.append(("sslmode", "disable"))
            elif low in ("prefer", "allow", "verify-ca", "verify-full"):
                translated.append(("sslmode", low))
            else:
                # неизвестное значение — безопасный дефолт
                translated.append(("sslmode", "require"))
        else:
            translated.append((key, value))

    new_query = urlencode(translated, doseq=False)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def _get_url() -> str:
    """Построить sync-URL для psycopg2 из ``DATABASE_URL``."""
    url = os.getenv("DATABASE_URL", "postgresql://code9:code9@postgres:5432/code9")
    return _translate_asyncpg_to_psycopg2(url)


target_metadata = MainBase.metadata


def run_migrations_offline() -> None:
    """Offline-режим: генерация SQL без подключения (для CI review)."""
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Online-режим: применяем миграции к боевой БД."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # Явно кладём версионную таблицу в public, чтобы не пересекаться с tenant.
            version_table="alembic_version",
            version_table_schema="public",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
