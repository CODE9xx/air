"""
Общие хелперы для ORM-моделей: server-side defaults, типы CITEXT/INET/JSONB,
функция-конструктор CHECK-констрейнтов для StrEnum.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from sqlalchemy import CheckConstraint, Column, text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

# Re-export for удобства импорта моделями.
__all__ = ["JSONB", "INET", "UUID", "uuid_pk", "now_default", "enum_check"]


def uuid_pk() -> Column:
    """Колонка ``id UUID PRIMARY KEY DEFAULT gen_random_uuid()``."""
    return Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        nullable=False,
    )


def now_default() -> Any:
    """Server-side default ``NOW()`` для TIMESTAMPTZ-колонок."""
    return text("NOW()")


def enum_check(column: str, enum_cls: type[Enum], name: str | None = None) -> CheckConstraint:
    """
    Сгенерировать ``CHECK (column IN (...))`` по значениям StrEnum.

    Используется как ``__table_args__`` дополнение к ``String``-колонке,
    чтобы не создавать Postgres ENUM-тип (см. enums.py — храним TEXT+CHECK).
    """
    values = ", ".join(f"'{v.value}'" for v in enum_cls)
    constraint_name = name or f"ck_{column}_enum"
    return CheckConstraint(f"{column} IN ({values})", name=constraint_name)
