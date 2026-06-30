"""Add agent_state and rendered_slides checkpoint columns to generation_tasks.

These columns back the new ReAct-driven orchestrator so a restarted
worker can resume from the last successful batch (M-evolve, US1).

Revision ID: 0009_generation_agent_state
Revises: 0008_generation_general_mode
Create Date: 2026-06-29 18:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_generation_agent_state"
down_revision = "0008_generation_general_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generation_tasks",
        sa.Column("agent_state", postgresql.JSONB, nullable=True),
    )
    op.add_column(
        "generation_tasks",
        sa.Column("rendered_slides", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("generation_tasks", "rendered_slides")
    op.drop_column("generation_tasks", "agent_state")
