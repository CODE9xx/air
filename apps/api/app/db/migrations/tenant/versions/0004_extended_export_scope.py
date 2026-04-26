"""Extended amoCRM export scope tables.

Revision ID: 0004_extended_export_scope
Revises: 0003_deal_products
Create Date: 2026-04-26
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0004_extended_export_scope"
down_revision: Union[str, None] = "0003_deal_products"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deal_contacts (
            deal_id UUID NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            is_primary BOOLEAN NOT NULL DEFAULT FALSE,
            raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT pk_deal_contacts PRIMARY KEY (deal_id, contact_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_deal_contacts_contact ON deal_contacts(contact_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deal_companies (
            deal_id UUID NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            is_primary BOOLEAN NOT NULL DEFAULT FALSE,
            raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT pk_deal_companies PRIMARY KEY (deal_id, company_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_deal_companies_company ON deal_companies(company_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deal_stage_transitions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            deal_id UUID NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
            event_external_id TEXT NOT NULL UNIQUE,
            from_stage_id UUID NULL REFERENCES stages(id),
            to_stage_id UUID NULL REFERENCES stages(id),
            changed_by_user_id UUID NULL REFERENCES crm_users(id),
            changed_at_external TIMESTAMPTZ NULL,
            raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_deal_stage_transitions_deal_time "
        "ON deal_stage_transitions(deal_id, changed_at_external)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_deal_stage_transitions_to_stage "
        "ON deal_stage_transitions(to_stage_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deal_sources (
            deal_id UUID NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
            source_name TEXT NULL,
            source_type TEXT NULL,
            utm_source TEXT NULL,
            utm_medium TEXT NULL,
            utm_campaign TEXT NULL,
            utm_content TEXT NULL,
            utm_term TEXT NULL,
            raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT pk_deal_sources PRIMARY KEY (deal_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_deal_sources_source ON deal_sources(source_name)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_deal_sources_utm "
        "ON deal_sources(utm_source, utm_medium, utm_campaign)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_custom_fields (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_type TEXT NOT NULL,
            external_id TEXT NOT NULL,
            name TEXT NULL,
            code TEXT NULL,
            field_type TEXT NULL,
            raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_crm_custom_fields_entity_external UNIQUE (entity_type, external_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_custom_fields_entity ON crm_custom_fields(entity_type)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_custom_field_values (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_type TEXT NOT NULL,
            entity_external_id TEXT NOT NULL,
            custom_field_id UUID NULL REFERENCES crm_custom_fields(id),
            field_external_id TEXT NOT NULL,
            field_name TEXT NULL,
            value_text TEXT NULL,
            value_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_crm_custom_field_values_entity_field
                UNIQUE (entity_type, entity_external_id, field_external_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_crm_custom_field_values_field "
        "ON crm_custom_field_values(custom_field_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_crm_custom_field_values_entity "
        "ON crm_custom_field_values(entity_type, entity_external_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS crm_custom_field_values")
    op.execute("DROP TABLE IF EXISTS crm_custom_fields")
    op.execute("DROP TABLE IF EXISTS deal_sources")
    op.execute("DROP TABLE IF EXISTS deal_stage_transitions")
    op.execute("DROP TABLE IF EXISTS deal_companies")
    op.execute("DROP TABLE IF EXISTS deal_contacts")
