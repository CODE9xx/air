"""
Хелпер: применить tenant-template миграции к указанной schema.

Используется:
- worker job'ом ``bootstrap_tenant_schema`` при активации CRM-подключения;
- CLI: ``python -m scripts.migrations.apply_tenant_template <schema>``;
- CI-скриптом при мерже новой tenant-миграции — прогоняем по всем active.

Все операции — sync (psycopg2). ``DATABASE_URL`` читается из env.

Изоляция от ``apps/api`` в worker-контейнере (Task #52.3, Bug C)
---------------------------------------------------------------
``scripts/`` монтируется в worker bind-mount'ом. Ранее файл импортировал
``from app.db.url_translate import asyncpg_to_psycopg2`` и полагался на
sys.path-хак, добавляющий ``<repo>/apps/api`` — но в worker-образе этого
пути не существовало, и bootstrap падал с ``ModuleNotFoundError``. Теперь
DSN-транслятор **дублируется inline** (см. ниже); tenant-alembic (env.py,
версии) по-прежнему читается с диска через ``_ALEMBIC_INI`` — для них
compose монтирует ``apps/api`` в worker read-only.

Три копии транслятора обязаны меняться одним коммитом:
  * apps/api/app/db/url_translate.py           (source of truth)
  * apps/worker/worker/lib/url_translate.py    (worker hot path mirror)
  * scripts/migrations/apply_tenant_template.py (этот файл, inline copy)
Контрактные тесты: ``tests/api/test_url_translate.py`` (31 case).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

_REPO_ROOT = Path(__file__).resolve().parents[2]

# CR-04 (QA, 2026-04-18): ужесточён regex — обязателен prefix crm_, защита от
# попадания зарезервированных имён PostgreSQL. Закрыто Lead Architect.
_SCHEMA_RE = re.compile(r"^crm_[a-z0-9][a-z0-9_]{1,59}$")

_ALEMBIC_INI = _REPO_ROOT / "apps" / "api" / "app" / "db" / "migrations" / "alembic.ini"


# ---------------------------------------------------------------------------
# INLINE asyncpg→psycopg2 translator (Task #52.3, Bug C).
# Контракт идентичен ``apps/api/app/db/url_translate.asyncpg_to_psycopg2``.
# Безопасность: функция НЕ логирует URL ни при каких обстоятельствах.
# ---------------------------------------------------------------------------

_SSL_TRUTHY = frozenset({"true", "require", "1"})
_SSL_FALSY = frozenset({"false", "disable", "0", ""})
_SSL_LIBPQ_PASSTHROUGH = frozenset({"prefer", "allow", "verify-ca", "verify-full"})


def asyncpg_to_psycopg2(url: str) -> str:
    """asyncpg DSN → psycopg2 DSN; ``ssl=…`` → ``sslmode=…``.

    Правила:
      * ``postgresql+asyncpg://…`` / ``postgres+asyncpg://…`` → ``postgresql+psycopg2://…``
      * ``ssl=require|true|1`` → ``sslmode=require``
      * ``ssl=disable|false|0|`` (пусто) → ``sslmode=disable``
      * ``ssl=prefer|allow|verify-ca|verify-full`` → то же значение под sslmode
      * любое иное → ``sslmode=require`` (безопасный дефолт для managed-Postgres)
      * tie-break: если ``sslmode`` уже присутствует, он выигрывает и ``ssl``
        отбрасывается.
      * username / password / host / path / прочие query-params сохраняются.
    """
    # 1. Схема/драйвер.
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql+psycopg2://" + url[len("postgresql+asyncpg://"):]
    elif url.startswith("postgres+asyncpg://"):
        url = "postgresql+psycopg2://" + url[len("postgres+asyncpg://"):]

    # 2. Query-params.
    parts = urlsplit(url)
    if not parts.query:
        return url

    qs = parse_qsl(parts.query, keep_blank_values=True)
    explicit_sslmode_present = any(k == "sslmode" for k, _ in qs)

    translated: list[tuple[str, str]] = []
    for key, value in qs:
        if key == "ssl":
            if explicit_sslmode_present:
                # Явный sslmode → ssl отбрасываем.
                continue
            low = value.strip().lower()
            if low in _SSL_TRUTHY:
                translated.append(("sslmode", "require"))
            elif low in _SSL_FALSY:
                translated.append(("sslmode", "disable"))
            elif low in _SSL_LIBPQ_PASSTHROUGH:
                translated.append(("sslmode", low))
            else:
                # Неизвестное значение — безопасный дефолт для managed-hosts.
                translated.append(("sslmode", "require"))
        else:
            translated.append((key, value))

    new_query = urlencode(translated, doseq=False)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def _sync_url() -> str:
    """Sync-URL (psycopg2) из ``DATABASE_URL``. DSN не логируется."""
    url = os.getenv("DATABASE_URL", "postgresql://code9:code9@postgres:5432/code9")
    return asyncpg_to_psycopg2(url)


def _validate_schema_name(schema: str) -> None:
    if not _SCHEMA_RE.fullmatch(schema):
        raise ValueError(f"Невалидное имя tenant-схемы: {schema!r}")


def ensure_schema(schema: str) -> None:
    """``CREATE SCHEMA IF NOT EXISTS "<schema>"`` — безопасно, с валидацией имени."""
    _validate_schema_name(schema)
    engine = create_engine(_sync_url(), future=True)
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    engine.dispose()


def _alembic_tenant_config(schema: str) -> Config:
    if not _ALEMBIC_INI.exists():
        raise RuntimeError(f"alembic.ini не найден по пути {_ALEMBIC_INI}")
    cfg = Config(str(_ALEMBIC_INI), ini_section="tenant")
    # Передаём schema в env.py через x-argument.
    cfg.cmd_opts = None
    cfg.attributes["schema"] = schema  # доступно в env.py как config.attributes
    # Альтернативный путь — через env var: env.py читает x_argument, но alembic
    # API через Config.attributes не проходит. Используем env var + x_argument.
    os.environ["ALEMBIC_TENANT_SCHEMA"] = schema
    # API alembic принимает x_argument только через CLI. Для программного
    # вызова используем private-атрибут: config.cmd_opts не всегда есть.
    # Простое решение: установим глобальный x через config.
    cfg.set_main_option("sqlalchemy.url", _sync_url())
    return cfg


def apply_tenant_template(schema: str) -> None:
    """
    Полный цикл: CREATE SCHEMA + apply alembic tenant migrations до head.

    Идемпотентна: повторный вызов на той же schema не ломает БД.
    """
    _validate_schema_name(schema)
    ensure_schema(schema)

    cfg = Config(str(_ALEMBIC_INI), ini_section="tenant")
    cfg.set_main_option("sqlalchemy.url", _sync_url())
    # Alembic поддерживает -x через config.attributes["x"] если вызывать
    # command API с **{ "x": ["schema=..."] }**, но самый простой путь —
    # modify CLI-args через config.cmd_opts. Проще: monkey-patch context
    # через env var + кастомный x_argument shim.
    #
    # Решение: передаём schema через ``config.cmd_opts.x`` — в alembic 1.13
    # это работает через Namespace с attr ``x``.
    from argparse import Namespace

    cfg.cmd_opts = Namespace(x=[f"schema={schema}"])

    command.upgrade(cfg, "head")


def drop_tenant_schema(schema: str) -> None:
    """``DROP SCHEMA "<schema>" CASCADE``. Используется worker-job'ом delete_connection_data."""
    _validate_schema_name(schema)
    engine = create_engine(_sync_url(), future=True)
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    engine.dispose()


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m scripts.migrations.apply_tenant_template <schema_name>")
        return 2
    schema = sys.argv[1]
    apply_tenant_template(schema)
    print(f"[apply_tenant_template] OK schema={schema}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
