"""Token wallet and ledger for export quotes.

Revision ID: 0004_token_wallet
Revises: 0003_pull_amocrm_job_kind
Create Date: 2026-04-24

Adds an internal AIC9-token balance, reservation, and ledger layer. This is
not an online payment integration: it only tracks service tokens used by
exports and later AI actions.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers.
revision: str = "0004_token_wallet"
down_revision: Union[str, None] = "0003_pull_amocrm_job_kind"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "token_accounts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_key", sa.Text(), nullable=False, server_default="free"),
        sa.Column("included_monthly_mtokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("balance_mtokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reserved_mtokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "plan_key IN ('free', 'paygo', 'start', 'team', 'pro')",
            name="ck_tokenacc_plan_key",
        ),
        sa.CheckConstraint(
            "included_monthly_mtokens >= 0",
            name="ck_tokenacc_included_nonnegative",
        ),
        sa.CheckConstraint("balance_mtokens >= 0", name="ck_tokenacc_balance_nonnegative"),
        sa.CheckConstraint("reserved_mtokens >= 0", name="ck_tokenacc_reserved_nonnegative"),
        sa.CheckConstraint(
            "reserved_mtokens <= balance_mtokens",
            name="ck_tokenacc_reserved_lte_balance",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", name="uq_token_accounts_workspace"),
    )
    op.create_index("ix_tokenacc_workspace", "token_accounts", ["workspace_id"])

    op.create_table(
        "token_reservations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("token_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crm_connection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount_mtokens", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="reserved"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('reserved', 'charged', 'released')",
            name="ck_tokenres_status",
        ),
        sa.CheckConstraint("amount_mtokens > 0", name="ck_tokenres_amount_positive"),
        sa.ForeignKeyConstraint(["token_account_id"], ["token_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["crm_connection_id"], ["crm_connections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_tokenres_job"),
    )
    op.create_index(
        "ix_tokenres_workspace_created",
        "token_reservations",
        ["workspace_id", "created_at"],
    )
    op.create_index("ix_tokenres_status_created", "token_reservations", ["status", "created_at"])
    op.create_index("ix_tokenres_connection", "token_reservations", ["crm_connection_id"])

    op.create_table(
        "token_ledger",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("token_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crm_connection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount_mtokens", sa.BigInteger(), nullable=False),
        sa.Column("balance_after_mtokens", sa.BigInteger(), nullable=False),
        sa.Column("reserved_after_mtokens", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "kind IN ('grant', 'purchase', 'reserve', 'charge', 'release', 'refund', 'adjustment')",
            name="ck_tokenledger_kind",
        ),
        sa.ForeignKeyConstraint(["token_account_id"], ["token_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["crm_connection_id"], ["crm_connections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reservation_id"], ["token_reservations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tokenledger_account_created", "token_ledger", ["token_account_id", "created_at"])
    op.create_index("ix_tokenledger_workspace_created", "token_ledger", ["workspace_id", "created_at"])
    op.create_index("ix_tokenledger_connection", "token_ledger", ["crm_connection_id"])
    op.create_index("ix_tokenledger_job", "token_ledger", ["job_id"])

    # Existing workspaces get token accounts with no free balance unless their
    # current legacy billing plan is explicitly mapped.
    op.execute(
        """
        INSERT INTO token_accounts(
            workspace_id, plan_key, included_monthly_mtokens, balance_mtokens, reserved_mtokens
        )
        SELECT
            workspace_id,
            CASE WHEN plan = 'team' THEN 'team' ELSE 'free' END,
            CASE WHEN plan = 'team' THEN 9000 * 1000 ELSE 0 END,
            CASE WHEN plan = 'team' THEN 9000 * 1000 ELSE 0 END,
            0
        FROM billing_accounts
        ON CONFLICT (workspace_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_tokenledger_job", table_name="token_ledger")
    op.drop_index("ix_tokenledger_connection", table_name="token_ledger")
    op.drop_index("ix_tokenledger_workspace_created", table_name="token_ledger")
    op.drop_index("ix_tokenledger_account_created", table_name="token_ledger")
    op.drop_table("token_ledger")

    op.drop_index("ix_tokenres_connection", table_name="token_reservations")
    op.drop_index("ix_tokenres_status_created", table_name="token_reservations")
    op.drop_index("ix_tokenres_workspace_created", table_name="token_reservations")
    op.drop_table("token_reservations")

    op.drop_index("ix_tokenacc_workspace", table_name="token_accounts")
    op.drop_table("token_accounts")
