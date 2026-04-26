"""Initial main schema — все public-таблицы.

Revision ID: 0001_initial_main
Revises:
Create Date: 2026-04-18

Создаёт весь public-слой CODE9 Analytics: users, workspaces, crm_connections,
billing, jobs, notifications, admin-таблицы, deletion_requests и полный
набор AI-таблиц.

Подход: используем ``MainBase.metadata.create_all(connection)`` — это даёт
нам ровно то, что описано в ORM (с индексами и CHECK-констрейнтами, не
завися от autogenerate-diff'ов). Для даунгрейда — ``drop_all``.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# Импорт моделей подтягивает все таблицы в MainBase.metadata.
from app.db.models import MainBase  # noqa: E402

# revision identifiers.
revision: str = "0001_initial_main"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Расширения: gen_random_uuid() + CITEXT (для email-полей).
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute('CREATE EXTENSION IF NOT EXISTS citext')

    bind = op.get_bind()
    MainBase.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    MainBase.metadata.drop_all(bind=bind)
    # Расширения НЕ удаляем — их могут использовать другие компоненты.
