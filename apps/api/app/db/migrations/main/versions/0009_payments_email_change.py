"""Payment orders and email-change verification purpose.

Revision ID: 0009_payments_email_change
Revises: 0008_email_connections
Create Date: 2026-04-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_payments_email_change"
down_revision: Union[str, None] = "0008_email_connections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EVC_PURPOSE_VALUES = (
    "email_verify",
    "password_reset",
    "connection_delete",
    "email_change",
)

BILLING_PLAN_VALUES = (
    "free",
    "paygo",
    "start",
    "team",
    "pro",
    "enterprise",
)


def _quoted(values: tuple[str, ...]) -> str:
    return ",".join(f"'{item}'" for item in values)


def _uuid_col() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )


def upgrade() -> None:
    op.drop_constraint("ck_evc_purpose", "email_verification_codes", type_="check")
    op.create_check_constraint(
        "ck_evc_purpose",
        "email_verification_codes",
        f"purpose IN ({_quoted(EVC_PURPOSE_VALUES)})",
    )

    op.drop_constraint("ck_billacc_plan", "billing_accounts", type_="check")
    op.create_check_constraint(
        "ck_billacc_plan",
        "billing_accounts",
        f"plan IN ({_quoted(BILLING_PLAN_VALUES)})",
    )

    op.create_table(
        "payment_orders",
        _uuid_col(),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False, server_default="tbank"),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default="RUB"),
        sa.Column("token_amount_mtokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("plan_key", sa.Text(), nullable=True),
        sa.Column("period_months", sa.Integer(), nullable=True),
        sa.Column("external_order_id", sa.Text(), nullable=False),
        sa.Column("external_payment_id", sa.Text(), nullable=True),
        sa.Column("payment_url", sa.Text(), nullable=True),
        sa.Column("invoice_number", sa.Text(), nullable=True),
        sa.Column("payer_inn", sa.Text(), nullable=True),
        sa.Column("payer_kpp", sa.Text(), nullable=True),
        sa.Column("payer_name", sa.Text(), nullable=True),
        sa.Column("payer_ogrn", sa.Text(), nullable=True),
        sa.Column("payer_address", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_order_id", name="uq_payorder_external_order"),
        sa.CheckConstraint("method IN ('card','invoice')", name="ck_payorder_method"),
        sa.CheckConstraint("purpose IN ('token_topup','subscription')", name="ck_payorder_purpose"),
        sa.CheckConstraint(
            "status IN ('pending','paid','failed','cancelled','manual_review')",
            name="ck_payorder_status",
        ),
        sa.CheckConstraint("amount_cents > 0", name="ck_payorder_amount_positive"),
        sa.CheckConstraint("token_amount_mtokens >= 0", name="ck_payorder_tokens_nonnegative"),
    )
    op.create_index("ix_payorder_workspace_created", "payment_orders", ["workspace_id", "created_at"])
    op.create_index("ix_payorder_status_created", "payment_orders", ["status", "created_at"])
    op.create_index("ix_payorder_external_payment", "payment_orders", ["external_payment_id"])


def downgrade() -> None:
    op.drop_index("ix_payorder_external_payment", table_name="payment_orders")
    op.drop_index("ix_payorder_status_created", table_name="payment_orders")
    op.drop_index("ix_payorder_workspace_created", table_name="payment_orders")
    op.drop_table("payment_orders")

    op.drop_constraint("ck_billacc_plan", "billing_accounts", type_="check")
    op.create_check_constraint(
        "ck_billacc_plan",
        "billing_accounts",
        "plan IN ('free','paygo','team')",
    )

    op.drop_constraint("ck_evc_purpose", "email_verification_codes", type_="check")
    op.create_check_constraint(
        "ck_evc_purpose",
        "email_verification_codes",
        "purpose IN ('email_verify','password_reset','connection_delete')",
    )
