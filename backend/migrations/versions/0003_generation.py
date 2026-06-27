"""Generation tasks + trace stages (T035) per data-model.md §6 + §7.

Revision ID: 0003_generation
Revises: 0002_idempotency
Create Date: 2026-06-24 00:02:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_generation"
down_revision = "0002_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── enums ───────────────────────────────────────────────────────
    task_status = postgresql.ENUM(
        "queued", "running", "success", "failed", "cancelled", "archived",
        name="task_status", create_type=True,
    )
    task_stage = postgresql.ENUM(
        "outline", "points", "svg", "pptx",
        name="task_stage", create_type=True,
    )
    stage_status = postgresql.ENUM(
        "pending", "running", "success", "failed",
        name="stage_status", create_type=True,
    )
    task_status.create(op.get_bind(), checkfirst=True)
    task_stage.create(op.get_bind(), checkfirst=True)
    stage_status.create(op.get_bind(), checkfirst=True)

    # ── generation_tasks ────────────────────────────────────────────
    op.create_table(
        "generation_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column(
            "sample_snapshot_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "queued", "running", "success", "failed", "cancelled", "archived",
                name="task_status", create_type=False,
            ),
            nullable=False,
            server_default="queued",
        ),
        sa.Column(
            "current_stage",
            postgresql.ENUM(
                "outline", "points", "svg", "pptx",
                name="task_stage", create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("queue_position", sa.Integer, nullable=True),
        sa.Column("result_pptx_path", sa.String(512), nullable=True),
        sa.Column("style_fit_score", postgresql.JSONB, nullable=True),
        sa.Column("token_consumed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("estimated_tokens", sa.Integer, nullable=True),
        sa.Column("estimated_seconds", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queue_deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index("idx_tasks_owner", "generation_tasks", ["owner_id"])
    op.create_index("idx_tasks_status", "generation_tasks", ["status"])
    op.create_index(
        "idx_tasks_owner_status_recent",
        "generation_tasks", ["owner_id", "status", "created_at"],
    )
    op.create_index(
        "idx_tasks_queue",
        "generation_tasks", ["status", "queue_position"],
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index("idx_tasks_expires", "generation_tasks", ["expires_at"])

    # ── trace_stages ────────────────────────────────────────────────
    op.create_table(
        "trace_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("generation_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_name", sa.String(32), nullable=False),
        sa.Column("stage_order", sa.SmallInteger, nullable=False),
        sa.Column("input_summary", sa.Text, nullable=False),
        sa.Column("output_summary", sa.Text, nullable=False),
        sa.Column(
            "referenced_sample_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "running", "success", "failed",
                name="stage_status", create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("redo_count", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("task_id", "stage_name", name="uq_trace_task_stage"),
    )
    op.create_index("idx_trace_task", "trace_stages", ["task_id"])
    op.create_index("idx_trace_task_order", "trace_stages", ["task_id", "stage_order"])


def downgrade() -> None:
    op.drop_index("idx_trace_task_order", table_name="trace_stages")
    op.drop_index("idx_trace_task", table_name="trace_stages")
    op.drop_table("trace_stages")

    op.drop_index("idx_tasks_expires", table_name="generation_tasks")
    op.drop_index("idx_tasks_queue", table_name="generation_tasks")
    op.drop_index("idx_tasks_owner_status_recent", table_name="generation_tasks")
    op.drop_index("idx_tasks_status", table_name="generation_tasks")
    op.drop_index("idx_tasks_owner", table_name="generation_tasks")
    op.drop_table("generation_tasks")

    op.execute("DROP TYPE IF EXISTS stage_status")
    op.execute("DROP TYPE IF EXISTS task_stage")
    op.execute("DROP TYPE IF EXISTS task_status")
