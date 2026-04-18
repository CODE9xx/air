"""
Хелпер: применить tenant-template миграции к указанной schema.

Используется:
- worker job'ом ``bootstrap_tenant_schema`` при активации CRM-подключения;
- CLI: ``python -m scripts.migrations.apply_tenant_template <schema>``;
- CI-скриптом при мерже новой tenant-миграции — прогоняем по всем active.

Все операции — sync (psycopg2). ``DATABASE_URL`` читается из env.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

# CR-04 (QA, 2026-04-18): ужесточён regex — обязателен prefix crm_, защита от
# попадания зарезервированных имён PostgreSQL. Закрыто Lead Architect.
_SCHEMA_RE = re.compile(r"^crm_[a-z0-9][a-z0-9_]{1,59}$")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "apps" / "api" / "app" / "db" / "migrations" / "alembic.ini"


def _sync_url() -> str:
    """Sync-URL (psycopg2) из ``DATABASE_URL``."""
    url = os.getenv("DATABASE_URL", "postgresql://code9:code9@postgres:5432/code9")
    return (
        url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        .replace("postgres+asyncpg://", "postgresql+psycopg2://")
    )


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
