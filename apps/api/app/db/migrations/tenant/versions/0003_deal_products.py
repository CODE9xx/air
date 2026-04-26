"""Deal linked catalog elements/products.

Revision ID: 0003_deal_products
Revises: 0002_email_messages
Create Date: 2026-04-26
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0003_deal_products"
down_revision: Union[str, None] = "0002_email_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0001_initial_tenant uses TenantBase.metadata.create_all(), so brand-new
    # schemas may already contain this table once the ORM model exists. Keep
    # this migration idempotent for both fresh and existing tenant schemas.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deal_products (
            deal_id UUID NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
            product_id UUID NULL REFERENCES products(id),
            external_id TEXT NOT NULL,
            catalog_id TEXT NULL,
            quantity NUMERIC(18, 4) NULL,
            price_cents BIGINT NULL,
            price_id TEXT NULL,
            raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT pk_deal_products PRIMARY KEY (deal_id, external_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_deal_products_product ON deal_products(product_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_deal_products_catalog ON deal_products(catalog_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS deal_products")
