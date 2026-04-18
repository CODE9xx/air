"""
Tenant-schema хелперы для worker'а.

Тонкая обёртка над ``scripts.migrations.apply_tenant_template``:
- ``apply_tenant_migrations(schema_name)`` — create schema + apply tenant alembic;
- ``drop_tenant_schema(schema_name)`` — DROP SCHEMA ... CASCADE.
- ``validate_schema_name(name)`` — защита от SQL-injection при DDL.
- ``generate_tenant_schema(provider)`` — ``crm_<provider>_<shortid>``.

**ADR (MVP упрощение).**
В ТЗ допускался простой путь: один ``tenant_ddl.sql`` + ``format('%I', schema)``.
Мы выбрали полноценный alembic-путь (каталог ``apps/api/app/db/migrations/tenant``),
потому что:
1. ORM-модели уже написаны BE и являются единым источником правды;
2. Alembic даёт историю миграций внутри каждой tenant-схемы (``alembic_version``),
   что понадобится для апгрейдов шаблона в V1;
3. Один и тот же ``env.py`` переиспользуется из CI-скрипта, ручного CLI
   (``python -m scripts.migrations.apply_tenant_template <schema>``) и worker-job'а
   ``bootstrap_tenant_schema``.
Ценой одной дополнительной зависимости (``alembic`` в worker'е) получаем
согласованность со SCHEMA.md без дубля DDL.

Имя схемы формируется как ``crm_<slug>_<shortid>``, где:
- ``slug`` ∈ ``amo | kommo | bx24`` (соответствует ``CrmProvider`` из enums).
- ``shortid`` — 8 hex-символов (md5(uuid4())[:8]).
"""
from __future__ import annotations

import hashlib
import re
import uuid

# Re-export реализации из scripts/, чтобы worker-jobs не лазили в другой каталог.
from scripts.migrations.apply_tenant_template import (
    apply_tenant_template as _apply_tenant_template,
    drop_tenant_schema as _drop_tenant_schema,
    ensure_schema as _ensure_schema,
)

_PROVIDER_SLUG: dict[str, str] = {
    "amocrm": "amo",
    "amo": "amo",
    "kommo": "kommo",
    "bitrix24": "bx24",
    "bx24": "bx24",
}

# CR-04 (QA, 2026-04-18): ужесточён regex — обязателен prefix crm_, защита от
# попадания зарезервированных имён (public, pg_catalog и т.д.). Закрыто Lead Architect.
_SCHEMA_NAME_RE = re.compile(r"^crm_[a-z0-9][a-z0-9_]{1,59}$")


def validate_schema_name(name: str) -> None:
    """Бросить ValueError, если имя не безопасно для DDL (``CREATE SCHEMA "<name>"``)."""
    if not _SCHEMA_NAME_RE.fullmatch(name):
        raise ValueError(f"Невалидное имя tenant-схемы: {name!r}")


def short_id() -> str:
    """8 hex-символов — совпадает с помощником ``_common.short_id``."""
    return hashlib.md5(uuid.uuid4().hex.encode()).hexdigest()[:8]


def generate_tenant_schema(provider: str) -> str:
    """Сформировать имя tenant-схемы: ``crm_<slug>_<shortid>``."""
    slug = _PROVIDER_SLUG.get(provider.lower(), "crm")
    return f"crm_{slug}_{short_id()}"


def apply_tenant_migrations(schema_name: str) -> None:
    """``CREATE SCHEMA IF NOT EXISTS "<name>"`` + alembic-tenant upgrade head."""
    validate_schema_name(schema_name)
    _apply_tenant_template(schema_name)


def drop_tenant_schema(schema_name: str) -> None:
    """``DROP SCHEMA IF EXISTS "<name>" CASCADE``. Идемпотентно."""
    validate_schema_name(schema_name)
    _drop_tenant_schema(schema_name)


def ensure_schema_exists(schema_name: str) -> None:
    """Только ``CREATE SCHEMA IF NOT EXISTS`` без применения миграций."""
    validate_schema_name(schema_name)
    _ensure_schema(schema_name)


__all__ = [
    "apply_tenant_migrations",
    "drop_tenant_schema",
    "ensure_schema_exists",
    "generate_tenant_schema",
    "validate_schema_name",
    "short_id",
]
