"""Security events (T099) per data-model.md §8.

Constitution §IV/FR-020: PII hits, auth failures, and bulk lifecycle events
are written here for the security dashboard + audit trail.

Revision ID: 0006_security_events
Revises: 0005_preferences
Create Date: 2026-06-24 00:05:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_security_events"
down_revision = "0005_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    security_event_type = postgresql.ENUM(
        "pii_hit", "pii_blocked", "pii_replaced", "pii_acknowledged",
        "unauth_access", "bulk_export", "bulk_delete",
        name="security_event_type", create_type=True,
    )
    security_action = postgresql.ENUM(
        "replace", "block", "allow",
        name="security_action", create_type=True,
    )
    security_event_type.create(op.get_bind(), checkfirst=True)
    security_action.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "security_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            postgresql.ENUM(
                "pii_hit", "pii_blocked", "pii_replaced", "pii_acknowledged",
                "unauth_access", "bulk_export", "bulk_delete",
                name="security_event_type", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("hit_field", sa.String(64), nullable=True),
        sa.Column(
            "action_taken",
            postgresql.ENUM(
                "replace", "block", "allow",
                name="security_action", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("related_resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("details", postgresql.JSONB, nullable=True),
    )
    op.create_index("idx_security_owner", "security_events", ["owner_id"])
    op.create_index("idx_security_event_type", "security_events", ["event_type"])
    op.create_index(
        "idx_security_owner_recent",
        "security_events", ["owner_id", "created_at"],
    )
    op.create_index(
        "idx_security_type_recent",
        "security_events", ["event_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_security_type_recent", table_name="security_events")
    op.drop_index("idx_security_owner_recent", table_name="security_events")
    op.drop_index("idx_security_event_type", table_name="security_events")
    op.drop_index("idx_security_owner", table_name="security_events")
    op.drop_table("security_events")
    op.execute("DROP TYPE IF EXISTS security_action")
    op.execute("DROP TYPE IF EXISTS security_event_type")
