"""Add general mode fields to generation_tasks.

Revision ID: 0008_generation_general_mode
Revises: 0007_materials_and_drafts
Create Date: 2026-06-26 12:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_generation_general_mode"
down_revision = "0007_materials_and_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create GenerationMode enum
    generation_mode = postgresql.ENUM(
        "knowledge_base", "general",
        name="generation_mode", create_type=True,
    )
    generation_mode.create(op.get_bind(), checkfirst=True)

    # Add new columns to generation_tasks
    op.add_column(
        "generation_tasks",
        sa.Column(
            "mode",
            postgresql.ENUM("knowledge_base", "general", name="generation_mode", create_type=False),
            nullable=False,
            server_default="knowledge_base",
        ),
    )
    op.add_column(
        "generation_tasks",
        sa.Column("visual_style", sa.String(64), nullable=True),
    )
    op.add_column(
        "generation_tasks",
        sa.Column("communication_mode", sa.String(64), nullable=True),
    )
    op.add_column(
        "generation_tasks",
        sa.Column(
            "source_file_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("generation_tasks", "source_file_ids")
    op.drop_column("generation_tasks", "communication_mode")
    op.drop_column("generation_tasks", "visual_style")
    op.drop_column("generation_tasks", "mode")
    op.execute("DROP TYPE IF EXISTS generation_mode")
