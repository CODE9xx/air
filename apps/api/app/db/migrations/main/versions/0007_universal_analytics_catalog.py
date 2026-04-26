"""Universal analytics catalog, field mapping, and tenant AI insights.

Revision ID: 0007_universal_analytics_catalog
Revises: 0006_dashboard_builder
Create Date: 2026-04-24
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers.
revision: str = "0007_universal_analytics_catalog"
down_revision: Union[str, None] = "0006_dashboard_builder"
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
        "crm_field_mappings",
        _uuid_col(),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crm_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False, server_default="amocrm"),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("metric_key", sa.Text(), nullable=False),
        sa.Column("field_id", sa.Text(), nullable=True),
        sa.Column("field_name", sa.Text(), nullable=True),
        sa.Column("field_type", sa.Text(), nullable=True),
        sa.Column("value_type", sa.Text(), nullable=False, server_default="string"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["crm_connection_id"], ["crm_connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("crm_connection_id", "metric_key", name="uq_crmfieldmap_conn_metric"),
        sa.CheckConstraint(
            "entity_type IN ('deal','contact','company','task','note','call','message')",
            name="ck_crmfieldmap_entity",
        ),
        sa.CheckConstraint("status IN ('active','disabled','missing')", name="ck_crmfieldmap_status"),
    )
    op.create_index("ix_crmfieldmap_workspace", "crm_field_mappings", ["workspace_id"])
    op.create_index("ix_crmfieldmap_connection", "crm_field_mappings", ["crm_connection_id"])

    op.create_table(
        "dashboard_templates",
        _uuid_col(),
        sa.Column("template_key", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("pages", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("widgets", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_key", name="uq_dashtpl_key"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_dashtpl_status"),
    )
    op.create_index("ix_dashtpl_category", "dashboard_templates", ["category"])
    op.create_index("ix_dashtpl_status", "dashboard_templates", ["status"])

    op.create_table(
        "ai_tenant_insights",
        _uuid_col(),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crm_connection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("analysis_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("insight_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["crm_connection_id"], ["crm_connections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["analysis_job_id"], ["ai_analysis_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "source_kind IN ('deal','call','message','email','chat','manager','pipeline')",
            name="ck_aitenant_source_kind",
        ),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_aitenant_status"),
    )
    op.create_index("ix_aitenant_workspace_created", "ai_tenant_insights", ["workspace_id", "created_at"])
    op.create_index("ix_aitenant_conn_type", "ai_tenant_insights", ["crm_connection_id", "insight_type"])
    op.create_index("ix_aitenant_job", "ai_tenant_insights", ["analysis_job_id"])


def downgrade() -> None:
    op.drop_index("ix_aitenant_job", table_name="ai_tenant_insights")
    op.drop_index("ix_aitenant_conn_type", table_name="ai_tenant_insights")
    op.drop_index("ix_aitenant_workspace_created", table_name="ai_tenant_insights")
    op.drop_table("ai_tenant_insights")
    op.drop_index("ix_dashtpl_status", table_name="dashboard_templates")
    op.drop_index("ix_dashtpl_category", table_name="dashboard_templates")
    op.drop_table("dashboard_templates")
    op.drop_index("ix_crmfieldmap_connection", table_name="crm_field_mappings")
    op.drop_index("ix_crmfieldmap_workspace", table_name="crm_field_mappings")
    op.drop_table("crm_field_mappings")
