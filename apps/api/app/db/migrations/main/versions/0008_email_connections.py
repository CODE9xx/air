"""Email connections for IMAP-first production import.

Revision ID: 0008_email_connections
Revises: 0007_universal_analytics_catalog
Create Date: 2026-04-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_email_connections"
down_revision: Union[str, None] = "0007_universal_analytics_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JOB_KIND_VALUES = (
    "fetch_crm_data",
    "normalize_tenant_data",
    "refresh_token",
    "build_export_zip",
    "run_audit_report",
    "analyze_conversation",
    "extract_patterns",
    "anonymize_artifact",
    "retention_warning",
    "retention_read_only",
    "retention_delete",
    "delete_connection_data",
    "recalc_balance",
    "issue_invoice",
    "bootstrap_tenant_schema",
    "pull_amocrm_core",
    "pull_email_imap",
)


def _uuid_col() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )


def upgrade() -> None:
    op.create_table(
        "email_connections",
        _uuid_col(),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crm_connection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("email_address", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("auth_type", sa.Text(), nullable=False, server_default="imap_password"),
        sa.Column("imap_host", sa.Text(), nullable=False),
        sa.Column("imap_port", sa.Integer(), nullable=False, server_default="993"),
        sa.Column("imap_ssl", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column(
            "folders",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("sync_scope", sa.Text(), nullable=False, server_default="crm_only"),
        sa.Column("period", sa.Text(), nullable=False, server_default="last_12_months"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "last_counts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["crm_connection_id"], ["crm_connections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "email_address", name="uq_emailconn_ws_email"),
        sa.CheckConstraint(
            "provider IN ('gmail','microsoft','yandex','imap')",
            name="ck_emailconn_provider",
        ),
        sa.CheckConstraint("auth_type IN ('imap_password')", name="ck_emailconn_auth_type"),
        sa.CheckConstraint("imap_port > 0 AND imap_port <= 65535", name="ck_emailconn_imap_port"),
        sa.CheckConstraint(
            "sync_scope IN ('crm_only','all_mailbox')",
            name="ck_emailconn_sync_scope",
        ),
        sa.CheckConstraint(
            "period IN ('last_12_months','current_year','all_time')",
            name="ck_emailconn_period",
        ),
        sa.CheckConstraint(
            "status IN ('pending','active','paused','error','deleted')",
            name="ck_emailconn_status",
        ),
    )
    op.create_index("ix_emailconn_workspace_status", "email_connections", ["workspace_id", "status"])
    op.create_index("ix_emailconn_crm", "email_connections", ["crm_connection_id"])

    op.drop_constraint("ck_job_kind", "jobs", type_="check")
    op.create_check_constraint(
        "ck_job_kind",
        "jobs",
        "kind IN (" + ",".join(f"'{item}'" for item in JOB_KIND_VALUES) + ")",
    )


def downgrade() -> None:
    op.drop_constraint("ck_job_kind", "jobs", type_="check")
    op.create_check_constraint(
        "ck_job_kind",
        "jobs",
        "kind IN (" + ",".join(f"'{item}'" for item in JOB_KIND_VALUES if item != "pull_email_imap") + ")",
    )
    op.drop_index("ix_emailconn_crm", table_name="email_connections")
    op.drop_index("ix_emailconn_workspace_status", table_name="email_connections")
    op.drop_table("email_connections")
