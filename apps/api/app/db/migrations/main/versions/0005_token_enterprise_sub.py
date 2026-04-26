"""Enterprise token plan and subscription expiry.

Revision ID: 0005_token_enterprise_sub
Revises: 0004_token_wallet
Create Date: 2026-04-24
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers.
revision: str = "0005_token_enterprise_sub"
down_revision: Union[str, None] = "0004_token_wallet"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "token_accounts",
        sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint("ck_tokenacc_plan_key", "token_accounts", type_="check")
    op.create_check_constraint(
        "ck_tokenacc_plan_key",
        "token_accounts",
        "plan_key IN ('free', 'paygo', 'start', 'team', 'pro', 'enterprise')",
    )


def downgrade() -> None:
    op.execute("UPDATE token_accounts SET plan_key = 'pro' WHERE plan_key = 'enterprise'")
    op.drop_constraint("ck_tokenacc_plan_key", "token_accounts", type_="check")
    op.create_check_constraint(
        "ck_tokenacc_plan_key",
        "token_accounts",
        "plan_key IN ('free', 'paygo', 'start', 'team', 'pro')",
    )
    op.drop_column("token_accounts", "subscription_expires_at")
