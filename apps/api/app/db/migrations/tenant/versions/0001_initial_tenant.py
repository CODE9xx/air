"""Initial tenant schema template — raw_* + normalized таблицы.

Revision ID: 0001_initial_tenant
Revises:
Create Date: 2026-04-18

Создаёт 14 raw_* таблиц + 16 нормализованных (итого **30 таблиц**) внутри
tenant-схемы. Имя схемы приходит из ``env.py`` через ``-x schema=<name>``;
в начале транзакции делается ``SET LOCAL search_path = "<schema>", public``,
поэтому ``create_all`` кладёт всё куда надо.

Требует ``pgcrypto`` (для ``gen_random_uuid()``) — включается main-миграцией.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from app.db.models import TenantBase  # noqa: E402

revision: str = "0001_initial_tenant"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # search_path уже выставлен env.py — create_all положит всё в tenant-схему.
    TenantBase.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    TenantBase.metadata.drop_all(bind=bind)
