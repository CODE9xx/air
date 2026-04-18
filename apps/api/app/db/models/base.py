"""
Declarative Bases для двух независимых схем БД.

- ``MainBase`` — таблицы schema ``public`` (main).
- ``TenantBase`` — таблицы шаблона tenant-схемы (``crm_<provider>_<shortid>``).

Оба класса используются разными alembic env'ами
(см. ``apps/api/app/db/migrations/main`` и ``.../tenant``).

Наследники Base — **только** SQLAlchemy-модели этого проекта. Backend-код
импортирует сущности из ``app.db.models``; сюда — только Base.
"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class MainBase(DeclarativeBase):
    """Базовый класс ORM для main-schema (public)."""


class TenantBase(DeclarativeBase):
    """Базовый класс ORM для tenant-schema template."""
