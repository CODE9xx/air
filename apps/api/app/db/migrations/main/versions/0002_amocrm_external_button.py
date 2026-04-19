"""amoCRM external_button mode (#44.6): per-install OAuth credentials.

Revision ID: 0002_amocrm_external_button
Revises: 0001_initial_main
Create Date: 2026-04-19

Добавляет к `crm_connections` колонки для хранения OAuth-credentials,
которые amoCRM присылает вебхуком в режиме "external_button":

* amocrm_auth_mode              TEXT        — static_client | external_button
* amocrm_client_id              TEXT        — per-installation client_id
* amocrm_client_secret_encrypted BYTEA      — Fernet-шифрованный secret
* amocrm_external_integration_id TEXT       — id интеграции в amoCRM
* amocrm_credentials_received_at TIMESTAMPTZ — когда webhook доставил

Плюс partial-index по `amocrm_external_integration_id` — webhook-handler
ищет connection именно по этому полю.

static_client-мигация безопасна: все новые колонки NULL-допустимы,
существующие подключения остаются рабочими без апдейта.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers.
revision: str = "0002_amocrm_external_button"
down_revision: Union[str, None] = "0001_initial_main"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "crm_connections",
        sa.Column("amocrm_auth_mode", sa.Text(), nullable=True),
    )
    op.add_column(
        "crm_connections",
        sa.Column("amocrm_client_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "crm_connections",
        sa.Column(
            "amocrm_client_secret_encrypted", sa.LargeBinary(), nullable=True
        ),
    )
    op.add_column(
        "crm_connections",
        sa.Column("amocrm_external_integration_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "crm_connections",
        sa.Column(
            "amocrm_credentials_received_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Partial index: NULL-значения подавляющего большинства подключений
    # (static_client) индексировать не нужно.
    op.create_index(
        "ix_crmconn_amo_integration",
        "crm_connections",
        ["amocrm_external_integration_id"],
        unique=False,
        postgresql_where=sa.text("amocrm_external_integration_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_crmconn_amo_integration", table_name="crm_connections")
    op.drop_column("crm_connections", "amocrm_credentials_received_at")
    op.drop_column("crm_connections", "amocrm_external_integration_id")
    op.drop_column("crm_connections", "amocrm_client_secret_encrypted")
    op.drop_column("crm_connections", "amocrm_client_id")
    op.drop_column("crm_connections", "amocrm_auth_mode")
