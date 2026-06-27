"""Init users + api_keys (T016).

Per data-model.md §1 + §1a. Includes:
- users table
- api_keys table with scope rotation
- enums: user_tier
- indexes per data-model.md

Revision ID: 0001_init_users
Revises:
Create Date: 2026-06-24 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_init_users"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── enums ───────────────────────────────────────────────────────
    user_tier = postgresql.ENUM(
        "personal", "team", "enterprise", name="user_tier", create_type=True
    )
    user_tier.create(op.get_bind(), checkfirst=True)

    # ── users ───────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column(
            "tier",
            postgresql.ENUM(
                "personal", "team", "enterprise",
                name="user_tier", create_type=False,
            ),
            nullable=False,
            server_default="personal",
        ),
        sa.Column(
            "active_sample_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("api_key_hash", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_users_email", "users", ["email"], unique=True)
    op.create_index("idx_users_tier", "users", ["tier"])
    op.create_index("idx_users_deleted_at", "users", ["deleted_at"])
    op.create_index(
        "idx_users_email_active",
        "users",
        ["email"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── api_keys (T016 / §1a) ───────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(8), nullable=False),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.String(64)),
            nullable=False,
            server_default="{generation:write}",
        ),
        sa.Column("rate_limit_per_min", sa.Integer, nullable=False, server_default="60"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("char_length(key_prefix) = 8", name="api_key_prefix_chk"),
        sa.CheckConstraint(
            "rate_limit_per_min > 0 AND rate_limit_per_min <= 1000",
            name="api_key_rate_chk",
        ),
    )
    op.create_index("idx_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)
    op.create_index("idx_api_keys_owner", "api_keys", ["owner_id"])
    op.create_index(
        "idx_api_keys_owner_active",
        "api_keys",
        ["owner_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_api_keys_owner_active", table_name="api_keys")
    op.drop_index("idx_api_keys_owner", table_name="api_keys")
    op.drop_index("idx_api_keys_key_hash", table_name="api_keys")
    op.drop_table("api_keys")

    op.drop_index("idx_users_email_active", table_name="users")
    op.drop_index("idx_users_deleted_at", table_name="users")
    op.drop_index("idx_users_tier", table_name="users")
    op.drop_index("idx_users_email", table_name="users")
    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS user_tier")
