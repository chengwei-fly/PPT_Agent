"""Knowledge base tables (T057): samples + parse_results + embeddings.

Per data-model.md §2 + §3 + §4. Includes:
- samples (FR-010 SHA-256 dedup)
- parse_results (1:1 with samples)
- embeddings (pgvector, 1536-d, HNSW index)
- HNSW index for cosine search

Requires: pgvector extension (provisioned by init.sql)

Revision ID: 0004_samples
Revises: 0003_generation
Create Date: 2026-06-24 00:03:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_samples"
down_revision = "0003_generation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgvector must exist (provided by infra/postgres/init.sql)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── enums ───────────────────────────────────────────────────────
    file_type = postgresql.ENUM("pptx", "pdf", "docx", name="file_type", create_type=True)
    parse_status = postgresql.ENUM(
        "pending", "parsing", "parsed", "failed",
        name="parse_status", create_type=True,
    )
    file_type.create(op.get_bind(), checkfirst=True)
    parse_status.create(op.get_bind(), checkfirst=True)

    # ── samples ─────────────────────────────────────────────────────
    op.create_table(
        "samples",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column(
            "file_type",
            postgresql.ENUM("pptx", "pdf", "docx", name="file_type", create_type=False),
            nullable=False,
        ),
        sa.Column("raw_path", sa.String(512), nullable=False),
        sa.Column(
            "parse_status",
            postgresql.ENUM(
                "pending", "parsing", "parsed", "failed",
                name="parse_status", create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("parse_page_count", sa.Integer, nullable=True),
        sa.Column("pii_summary", postgresql.JSONB, nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("owner_id", "file_hash", name="uq_samples_owner_hash"),
        sa.CheckConstraint("char_length(file_hash) = 64", name="samples_hash_sha256_chk"),
    )
    op.create_index("idx_samples_owner", "samples", ["owner_id"])
    op.create_index("idx_samples_parse_status", "samples", ["parse_status"])
    op.create_index("idx_samples_owner_active", "samples", ["owner_id", "deleted_at"])
    op.create_index("idx_samples_file_hash", "samples", ["file_hash"])

    # ── parse_results (1:1 with samples) ────────────────────────────
    op.create_table(
        "parse_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "sample_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("samples.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("structure_json", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("parse_version", sa.String(16), nullable=False),
        sa.Column("parse_started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("parse_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )

    # ── embeddings (pgvector) ───────────────────────────────────────
    # Dimension is taken from settings via raw SQL — defaults to 1536 (OpenAI text-embedding-3-small)
    op.execute(
        "CREATE TABLE embeddings ("
        "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  sample_id UUID NOT NULL REFERENCES samples(id) ON DELETE CASCADE,"
        "  chunk_index INTEGER NOT NULL,"
        "  chunk_text TEXT NOT NULL,"
        "  vector vector(1536) NOT NULL,"
        "  model_name VARCHAR(64) NOT NULL,"
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        "  CONSTRAINT uq_embeddings_sample_chunk UNIQUE (sample_id, chunk_index),"
        "  CONSTRAINT embeddings_chunk_index_nonneg CHECK (chunk_index >= 0)"
        ")"
    )
    # HNSW index for cosine distance (per data-model.md §4)
    op.execute(
        "CREATE INDEX idx_embeddings_vector_hnsw ON embeddings "
        "USING hnsw (vector vector_cosine_ops)"
    )
    op.create_index("idx_embeddings_sample", "embeddings", ["sample_id"])


def downgrade() -> None:
    op.drop_index("idx_embeddings_sample", table_name="embeddings")
    op.execute("DROP INDEX IF EXISTS idx_embeddings_vector_hnsw")
    op.execute("DROP TABLE IF EXISTS embeddings")

    op.drop_table("parse_results")

    op.drop_index("idx_samples_file_hash", table_name="samples")
    op.drop_index("idx_samples_owner_active", table_name="samples")
    op.drop_index("idx_samples_parse_status", table_name="samples")
    op.drop_index("idx_samples_owner", table_name="samples")
    op.drop_table("samples")

    op.execute("DROP TYPE IF EXISTS parse_status")
    op.execute("DROP TYPE IF EXISTS file_type")
