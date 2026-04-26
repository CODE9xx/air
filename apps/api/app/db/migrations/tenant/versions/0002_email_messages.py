"""Tenant email messages imported from IMAP.

Revision ID: 0002_email_messages
Revises: 0001_initial_tenant
Create Date: 2026-04-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_email_messages"
down_revision: Union[str, None] = "0001_initial_tenant"
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
        "email_messages",
        _uuid_col(),
        sa.Column("email_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("folder", sa.Text(), nullable=False),
        sa.Column("uid", sa.Text(), nullable=True),
        sa.Column("message_id", sa.Text(), nullable=True),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_preview", sa.Text(), nullable=True),
        sa.Column("from_name", sa.Text(), nullable=True),
        sa.Column("from_email_hash", sa.Text(), nullable=True),
        sa.Column(
            "to_email_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "cc_email_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "participant_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("has_attachments", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("attachments_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "raw_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email_connection_id", "external_id", name="uq_emailmsg_conn_external"),
    )
    op.create_index("ix_emailmsg_conn_sent", "email_messages", ["email_connection_id", "sent_at"])
    op.create_index("ix_emailmsg_from_hash", "email_messages", ["from_email_hash"])
    op.create_index("ix_emailmsg_folder", "email_messages", ["folder"])


def downgrade() -> None:
    op.drop_index("ix_emailmsg_folder", table_name="email_messages")
    op.drop_index("ix_emailmsg_from_hash", table_name="email_messages")
    op.drop_index("ix_emailmsg_conn_sent", table_name="email_messages")
    op.drop_table("email_messages")
