"""Dashboard builder and share links.

Revision ID: 0006_dashboard_builder
Revises: 0005_token_enterprise_sub
Create Date: 2026-04-24
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers.
revision: str = "0006_dashboard_builder"
down_revision: Union[str, None] = "0005_token_enterprise_sub"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_col() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )


def upgrade() -> None:
    op.create_table(
        "dashboards",
        _uuid_col(),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crm_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.Text(), nullable=False, server_default="Основной дашборд"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["crm_connection_id"], ["crm_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("crm_connection_id", "name", name="uq_dash_conn_name"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_dash_status"),
    )
    op.create_index("ix_dash_ws", "dashboards", ["workspace_id"])
    op.create_index("ix_dash_conn", "dashboards", ["crm_connection_id"])

    op.create_table(
        "dashboard_widgets",
        _uuid_col(),
        sa.Column("dashboard_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("widget_key", sa.Text(), nullable=False),
        sa.Column("widget_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("y", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("w", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("h", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["dashboard_id"], ["dashboards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dashboard_id", "widget_key", name="uq_dash_widget_key"),
        sa.CheckConstraint("w >= 2 AND w <= 12", name="ck_dash_widget_w"),
        sa.CheckConstraint("h >= 2 AND h <= 12", name="ck_dash_widget_h"),
    )
    op.create_index("ix_dash_widget_dash", "dashboard_widgets", ["dashboard_id"])

    op.create_table(
        "dashboard_shares",
        _uuid_col(),
        sa.Column("dashboard_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["dashboard_id"], ["dashboards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_dashlink_hash"),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_dashshare_status"),
    )
    op.create_index("ix_dashshare_dash_status", "dashboard_shares", ["dashboard_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_dashshare_dash_status", table_name="dashboard_shares")
    op.drop_table("dashboard_shares")
    op.drop_index("ix_dash_widget_dash", table_name="dashboard_widgets")
    op.drop_table("dashboard_widgets")
    op.drop_index("ix_dash_conn", table_name="dashboards")
    op.drop_index("ix_dash_ws", table_name="dashboards")
    op.drop_table("dashboards")
