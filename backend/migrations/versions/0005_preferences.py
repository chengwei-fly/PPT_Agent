"""Preferences (T076) per data-model.md §5.

Constitution §V: source_chains preserves the original modification history
so the LLM can show users exactly which edits taught it a rule.

Revision ID: 0005_preferences
Revises: 0004_samples
Create Date: 2026-06-24 00:04:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_preferences"
down_revision = "0004_samples"
branch_labels = None
depends_on = None


def upgrade() -> None:
    preference_scope = postgresql.ENUM(
        "cover", "toc", "body", "closing", "all",
        name="preference_scope", create_type=True,
    )
    preference_scope.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "preferences",
        sa.Column("id", sa.String(16), primary_key=True),  # "P-007"
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_chains", postgresql.JSONB, nullable=False),
        sa.Column("rule_text", sa.Text, nullable=False),
        sa.Column(
            "applies_to",
            postgresql.ENUM(
                "cover", "toc", "body", "closing", "all",
                name="preference_scope", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("apply_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ignore_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_preferences_owner", "preferences", ["owner_id"])
    op.create_index(
        "idx_preferences_owner_active",
        "preferences", ["owner_id", "is_active"],
    )
    op.create_index(
        "idx_preferences_owner_recent",
        "preferences", ["owner_id", "last_applied_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_preferences_owner_recent", table_name="preferences")
    op.drop_index("idx_preferences_owner_active", table_name="preferences")
    op.drop_index("idx_preferences_owner", table_name="preferences")
    op.drop_table("preferences")
    op.execute("DROP TYPE IF EXISTS preference_scope")
