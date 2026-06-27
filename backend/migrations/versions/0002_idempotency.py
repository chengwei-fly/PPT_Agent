"""Idempotency keys (T016a) per contracts/api-design.md §15.1.

24h TTL, body-hash dedup, response replay.

Revision ID: 0002_idempotency
Revises: 0001_init_users
Create Date: 2026-06-24 00:01:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_idempotency"
down_revision = "0001_init_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("path", sa.String(256), nullable=False),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer, nullable=False, server_default="0"),
        sa.Column("response_body", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_idempotency_key", "idempotency_keys", ["key"])
    op.create_index("idx_idempotency_owner", "idempotency_keys", ["owner_id"])
    op.create_index("idx_idempotency_expires", "idempotency_keys", ["expires_at"])
    op.create_index(
        "uq_idempotency_key_method_path",
        "idempotency_keys",
        ["key", "method", "path"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_idempotency_key_method_path", table_name="idempotency_keys")
    op.drop_index("idx_idempotency_expires", table_name="idempotency_keys")
    op.drop_index("idx_idempotency_owner", table_name="idempotency_keys")
    op.drop_index("idx_idempotency_key", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
