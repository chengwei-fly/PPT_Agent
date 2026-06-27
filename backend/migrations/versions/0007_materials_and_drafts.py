"""US6: Materials & drafts (T200) per data-model.md §2.2.10-13.

Includes:
- slide_assets (per-page reusable material)
- drafts + draft_slides (with optimistic locking)
- material_search_index (BM25 + tsvector for hybrid search)
- draft_export_jobs (async PPTX export tracking)
- Triggers for search index sync + orphan-safe deletion
- 4 RLS policies (multi-tenant isolation)

Revision ID: 0007_materials_and_drafts
Revises: 0006_security_events
Create Date: 2026-06-24 00:06:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_materials_and_drafts"
down_revision = "0006_security_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── enums ───────────────────────────────────────────────────────
    slide_visual_type = postgresql.ENUM(
        "cover", "toc", "architecture", "flowchart", "data",
        "body", "closing", "mixed",
        name="slide_visual_type", create_type=True,
    )
    draft_status = postgresql.ENUM(
        "active", "archived", "exported",
        name="draft_status", create_type=True,
    )
    draft_slide_source_type = postgresql.ENUM(
        "reused", "generated", "manual",
        name="draft_slide_source_type", create_type=True,
    )
    slide_visual_type.create(op.get_bind(), checkfirst=True)
    draft_status.create(op.get_bind(), checkfirst=True)
    draft_slide_source_type.create(op.get_bind(), checkfirst=True)

    # ── slide_assets ────────────────────────────────────────────────
    op.create_table(
        "slide_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "source_sample_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("samples.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("page_index", sa.Integer, nullable=False),
        sa.Column(
            "visual_type",
            postgresql.ENUM(
                "cover", "toc", "architecture", "flowchart", "data",
                "body", "closing", "mixed",
                name="slide_visual_type", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("body_text", sa.Text, nullable=True),
        sa.Column("svg_payload", sa.Text, nullable=True),
        sa.Column("thumbnail_path", sa.String(512), nullable=True),
        sa.Column(
            "color_palette",
            postgresql.ARRAY(sa.String(16)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("font_family", sa.String(64), nullable=True),
        sa.Column(
            "industry_tags",
            postgresql.ARRAY(sa.String(32)),
            nullable=False,
            server_default="{}",
        ),
        # Embedding is stored as vector(1536) but we declare JSONB in ORM
        # for cross-dialect compat. Actual column type added below via raw SQL.
        sa.Column("embedding", postgresql.JSONB, nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # pgvector column for the actual embedding vector (separate from JSONB metadata)
    op.execute("ALTER TABLE slide_assets ADD COLUMN embedding_vector vector(1536)")
    op.execute(
        "CREATE INDEX idx_slide_assets_embedding_hnsw ON slide_assets "
        "USING hnsw (embedding_vector vector_cosine_ops)"
    )
    op.create_index("idx_slide_assets_visual_type", "slide_assets", ["visual_type"])
    op.create_index(
        "idx_slide_assets_industry",
        "slide_assets", ["industry_tags"], postgresql_using="gin",
    )
    op.create_index("idx_slide_assets_source", "slide_assets", ["source_sample_id"])
    op.create_index("idx_slide_assets_source_active", "slide_assets", ["source_sample_id"],
                    postgresql_where=sa.text("source_sample_id IS NOT NULL"))
    op.create_index("idx_slide_assets_deleted", "slide_assets", ["deleted_at"])

    # ── drafts ──────────────────────────────────────────────────────
    op.create_table(
        "drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active", "archived", "exported",
                name="draft_status", create_type=False,
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column("overall_style", postgresql.JSONB, nullable=True),
        sa.Column("last_saved_revision", sa.Integer, nullable=False, server_default="0"),
        sa.Column("editor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lock_acquired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_drafts_owner", "drafts", ["owner_id"])
    op.create_index("idx_drafts_owner_status", "drafts", ["owner_id", "status"])
    op.create_index(
        "idx_drafts_lock_expiry",
        "drafts", ["lock_expires_at"],
        postgresql_where=sa.text("lock_expires_at IS NOT NULL"),
    )

    # ── draft_slides ────────────────────────────────────────────────
    op.create_table(
        "draft_slides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "draft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("drafts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slide_order", sa.Integer, nullable=False),
        sa.Column(
            "source_type",
            postgresql.ENUM(
                "reused", "generated", "manual",
                name="draft_slide_source_type", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "material_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("slide_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "generated_stage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trace_stages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("materialized_svg", sa.Text, nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("body_text", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("style_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("draft_id", "slide_order", name="uq_draft_slides_order"),
        sa.CheckConstraint("slide_order >= 0", name="draft_slides_order_nonneg"),
    )
    op.create_index("idx_draft_slides_draft", "draft_slides", ["draft_id"])
    op.create_index("idx_draft_slides_material", "draft_slides", ["material_id"])

    # ── material_search_index ───────────────────────────────────────
    op.create_table(
        "material_search_index",
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("slide_assets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("body_text", sa.Text, nullable=True),
        sa.Column("visual_type", sa.String(32), nullable=False),
        sa.Column(
            "industry_tags",
            postgresql.ARRAY(sa.String(32)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("source_sample_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("search_tsv", postgresql.TSVECTOR, nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute(
        "CREATE INDEX idx_material_search_tsv ON material_search_index "
        "USING gin (search_tsv)"
    )
    op.create_index("idx_material_search_visual", "material_search_index", ["visual_type"])
    op.create_index("idx_material_search_source", "material_search_index", ["source_sample_id"])

    # ── draft_export_jobs ───────────────────────────────────────────
    op.create_table(
        "draft_export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "draft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("drafts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("pptx_path", sa.String(512), nullable=True),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_export_jobs_draft", "draft_export_jobs", ["draft_id"])
    op.create_index("idx_export_jobs_status", "draft_export_jobs", ["status"])

    # ── Triggers ────────────────────────────────────────────────────
    # Sync slide_assets → material_search_index on insert/update
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sync_slide_to_search_index() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO material_search_index (
                asset_id, title, body_text, visual_type,
                industry_tags, source_sample_id, indexed_at
            ) VALUES (
                NEW.id, NEW.title, NEW.body_text, NEW.visual_type::text,
                NEW.industry_tags, NEW.source_sample_id, now()
            )
            ON CONFLICT (asset_id) DO UPDATE SET
                title = EXCLUDED.title,
                body_text = EXCLUDED.body_text,
                visual_type = EXCLUDED.visual_type,
                industry_tags = EXCLUDED.industry_tags,
                source_sample_id = EXCLUDED.source_sample_id,
                search_tsv = setweight(to_tsvector('simple', coalesce(NEW.title, '')), 'A')
                          || setweight(to_tsvector('simple', coalesce(NEW.body_text, '')), 'B'),
                indexed_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_slide_assets_sync_search
        AFTER INSERT OR UPDATE ON slide_assets
        FOR EACH ROW EXECUTE FUNCTION sync_slide_to_search_index();
        """
    )
    # On sample soft-delete, NULL-out slide_assets.source_sample_id (orphan-safe)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION orphan_slide_assets_on_sample_delete() RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL THEN
                UPDATE slide_assets
                SET source_sample_id = NULL
                WHERE source_sample_id = NEW.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_sample_delete_orphan_assets
        AFTER UPDATE OF deleted_at ON samples
        FOR EACH ROW EXECUTE FUNCTION orphan_slide_assets_on_sample_delete();
        """
    )

    # ── RLS policies (multi-tenant isolation) ───────────────────────
    # Enable RLS on all owner-scoped tables
    for tbl in ("samples", "preferences", "generation_tasks",
                "security_events", "drafts"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        # Note: actual policy creation requires the session to have a
        # `current_owner_id` GUC. Policy is set up to filter rows by
        # owner_id for non-superuser connections.
        op.execute(
            f"""
            CREATE POLICY owner_isolation_{tbl} ON {tbl}
            USING (owner_id::text = current_setting('app.current_owner_id', true))
            """
        )


def downgrade() -> None:
    # Drop RLS policies first
    for tbl in ("drafts", "security_events", "generation_tasks",
                "preferences", "samples"):
        op.execute(f"DROP POLICY IF EXISTS owner_isolation_{tbl} ON {tbl}")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY")

    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS trg_sample_delete_orphan_assets ON samples")
    op.execute("DROP TRIGGER IF EXISTS trg_slide_assets_sync_search ON slide_assets")
    op.execute("DROP FUNCTION IF EXISTS orphan_slide_assets_on_sample_delete()")
    op.execute("DROP FUNCTION IF EXISTS sync_slide_to_search_index()")

    # Drop tables in reverse FK order
    op.drop_index("idx_export_jobs_status", table_name="draft_export_jobs")
    op.drop_index("idx_export_jobs_draft", table_name="draft_export_jobs")
    op.drop_table("draft_export_jobs")

    op.drop_index("idx_material_search_source", table_name="material_search_index")
    op.drop_index("idx_material_search_visual", table_name="material_search_index")
    op.execute("DROP INDEX IF EXISTS idx_material_search_tsv")
    op.drop_table("material_search_index")

    op.drop_index("idx_draft_slides_material", table_name="draft_slides")
    op.drop_index("idx_draft_slides_draft", table_name="draft_slides")
    op.drop_table("draft_slides")

    op.drop_index("idx_drafts_lock_expiry", table_name="drafts")
    op.drop_index("idx_drafts_owner_status", table_name="drafts")
    op.drop_index("idx_drafts_owner", table_name="drafts")
    op.drop_table("drafts")

    op.drop_index("idx_slide_assets_deleted", table_name="slide_assets")
    op.drop_index("idx_slide_assets_source_active", table_name="slide_assets")
    op.drop_index("idx_slide_assets_source", table_name="slide_assets")
    op.drop_index("idx_slide_assets_industry", table_name="slide_assets")
    op.drop_index("idx_slide_assets_visual_type", table_name="slide_assets")
    op.execute("DROP INDEX IF EXISTS idx_slide_assets_embedding_hnsw")
    op.execute("ALTER TABLE slide_assets DROP COLUMN IF EXISTS embedding_vector")
    op.drop_table("slide_assets")

    op.execute("DROP TYPE IF EXISTS draft_slide_source_type")
    op.execute("DROP TYPE IF EXISTS draft_status")
    op.execute("DROP TYPE IF EXISTS slide_visual_type")
