"""CuratedImporter — wires extractor + classifier + storage + DB.

The importer is the single entry point that turns a directory of PPTX files
into a population of ``slide_assets`` rows marked as ``curated`` (visible to
all users). It is the curator's equivalent of the per-user sample upload
pipeline.

Key properties:

* **Orphan assets** — ``source_sample_id`` is ``NULL``; the assets show up
  in :class:`MaterialSearchService` with ``include_orphan=True``
* **Idempotent** — re-running with the same ``source_file`` updates the
  existing asset rather than creating a duplicate. We dedupe on
  ``(source_file, page_index, shape_name)`` stored in ``metadata_json``
* **Resumable** — failures (network, LLM, MinIO) are logged per-asset and
  the loop continues; a partial import is still committed
* **Embedding aware** — after a successful insert we delegate to
  :func:`ensure_embedding_for_asset` so search and the existing
  :class:`MaterialSearchService` work without any further wiring
* **Optional LLM** — when no API key is present we fall back to
  :class:`HeuristicClassifier` so the import is always runnable in dev
"""

from __future__ import annotations

import asyncio
import io
import json
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.observability import get_logger
from src.db.models import SlideAsset, SlideVisualType
from src.services.parsing.embed_writer import ensure_embedding_for_asset
from src.services.material_importer.classifier import (
    ClassificationResult,
    make_cached_classify,
)
from src.services.material_importer.extractor import (
    ExtractedAsset,
    PPTXExtractor,
    discover_pptx_files,
)
from src.storage import minio as minio_store

logger = get_logger("material_importer.importer")

# Storage layout under the hot bucket:
#   materials/curated/thumbnails/<asset_id>.jpg
#   materials/curated/originals/<asset_id>.<ext>
THUMB_BUCKET = "ppt-hot"  # shared with hot bucket per current minio.py
THUMB_PREFIX = "materials/curated/thumbnails"
ORIGINAL_PREFIX = "materials/curated/originals"


@dataclass
class ImportReport:
    """Per-run summary surfaced to the CLI and admin API."""

    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    files_seen: int = 0
    files_failed: int = 0
    assets_extracted: int = 0
    assets_inserted: int = 0
    assets_updated: int = 0
    assets_skipped: int = 0
    classification_counts: dict[str, int] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    inserted_ids: list[str] = field(default_factory=list)

    def record(self, c: ClassificationResult) -> None:
        self.classification_counts[c.used] = self.classification_counts.get(c.used, 0) + 1
        vt = c.visual_type.value
        self.classification_counts[f"vt:{vt}"] = self.classification_counts.get(f"vt:{vt}", 0) + 1

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "files_seen": self.files_seen,
            "files_failed": self.files_failed,
            "assets_extracted": self.assets_extracted,
            "assets_inserted": self.assets_inserted,
            "assets_updated": self.assets_updated,
            "assets_skipped": self.assets_skipped,
            "classification_counts": self.classification_counts,
            "failures": self.failures[:50],
            "inserted_ids": self.inserted_ids,
        }


# ────────────────────────────────────────────────────────────────────
# Importer
# ────────────────────────────────────────────────────────────────────


class CuratedImporter:
    """Stateless importer. Holds config; one instance per run."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        use_llm: bool = True,
        llm_model: str | None = None,
        thumbnail_bucket: str = THUMB_BUCKET,
        concurrency: int = 4,
    ) -> None:
        self.session = session
        self.use_llm = use_llm
        self.llm_model = llm_model
        self.thumbnail_bucket = thumbnail_bucket
        self.concurrency = max(1, concurrency)
        self._classify = make_cached_classify(
            prefer_llm=use_llm, llm_model=llm_model
        )

    async def import_directory(
        self,
        directory: str | Path,
        *,
        dry_run: bool = False,
        max_assets: int | None = None,
        auto_convert_legacy: bool = True,
    ) -> ImportReport:
        """Scan ``directory`` and write all extracted assets to the DB.

        ``max_assets`` is a hard cap useful for testing.
        ``auto_convert_legacy`` attempts to convert ``.ppt`` files via
        LibreOffice / PowerPoint COM before extraction. Set to ``False``
        to skip legacy files.
        """
        report = ImportReport()
        extractor = PPTXExtractor()
        sem = asyncio.Semaphore(self.concurrency)

        async def _process_file(path: Path) -> None:
            nonlocal report
            # Handle legacy .ppt transparently
            if path.suffix.lower() == ".ppt" and auto_convert_legacy:
                try:
                    from src.services.material_importer.extractor import (
                        convert_legacy_ppt,
                    )

                    converted = convert_legacy_ppt(path)
                    path = converted
                    logger.info("legacy_ppt_converted", source=path.name)
                except Exception as e:  # noqa: BLE001
                    report.files_failed += 1
                    report.failures.append(
                        f"{path.name}: legacy .ppt convert failed: {e}"
                    )
                    logger.warning(
                        "legacy_ppt_convert_failed", file=path.name, error=str(e)
                    )
                    return
            try:
                assets = extractor.extract(path)
            except Exception as e:  # noqa: BLE001
                report.files_failed += 1
                report.failures.append(f"{path.name}: extract failed: {e}")
                logger.error("import_extract_failed", file=path.name, error=str(e))
                return
            report.files_seen += 1
            report.assets_extracted += len(assets)
            for asset in assets:
                if max_assets is not None and report.assets_inserted + report.assets_updated >= max_assets:
                    report.assets_skipped += 1
                    continue
                async with sem:
                    await self._process_one(asset, report, dry_run=dry_run)

        # Run files sequentially to keep the per-file log readable; the
        # per-asset classification is fanned out via the semaphore.
        for path in discover_pptx_files(directory):
            await _process_file(path)
        report.finished_at = datetime.utcnow()
        logger.info(
            "import_directory_done",
            files=report.files_seen,
            files_failed=report.files_failed,
            inserted=report.assets_inserted,
            updated=report.assets_updated,
            skipped=report.assets_skipped,
            dry_run=dry_run,
        )
        return report

    async def _process_one(
        self,
        asset: ExtractedAsset,
        report: ImportReport,
        *,
        dry_run: bool,
    ) -> None:
        try:
            classification = await self._classify(asset)
            report.record(classification)

            if dry_run:
                report.assets_skipped += 1
                return

            existing = await self._find_existing(asset)
            # Upload thumbnail to MinIO regardless (idempotent overwrites OK)
            thumb_key = f"{THUMB_PREFIX}/{asset.source_file}#{asset.slide_index}#{asset.shape_name}.jpg"
            original_key = (
                f"{ORIGINAL_PREFIX}/{asset.source_file}#{asset.slide_index}#{asset.shape_name}.{asset.image_ext}"
            )
            try:
                minio_store.put_object(
                    self.thumbnail_bucket,
                    thumb_key,
                    asset.image_bytes,
                    content_type=asset.mime_type or "image/jpeg",
                )
                # Originals are useful for hi-res view. We re-use the
                # thumbnail bytes here (we don't keep the raw blob) but the
                # key is recorded so the front-end can request an upgrade
                # path later.
                minio_store.put_object(
                    self.thumbnail_bucket,
                    original_key,
                    asset.image_bytes,
                    content_type=asset.mime_type or "image/jpeg",
                )
            except Exception as e:  # noqa: BLE001
                report.failures.append(
                    f"{asset.source_file}#{asset.slide_index}: storage failed: {e}"
                )
                logger.warning("minio_put_failed", error=str(e))
                return

            thumbnail_url = f"s3://{self.thumbnail_bucket}/{thumb_key}"
            meta = {
                "curated": True,
                "source_file": asset.source_file,
                "shape_name": asset.shape_name,
                "original_ext": asset.image_ext,
                "original_key": original_key,
                "classification": {
                    "used": classification.used,
                    "rationale": classification.rationale,
                },
            }

            if existing is not None:
                # Update in place
                existing.visual_type = classification.visual_type
                existing.title = classification.title or existing.title
                existing.industry_tags = classification.industry_tags or existing.industry_tags
                existing.color_palette = asset.palette or existing.color_palette
                existing.thumbnail_path = thumbnail_url
                existing.metadata_json = {**existing.metadata_json, **meta}
                existing.body_text = asset.text or existing.body_text
                existing.font_family = existing.font_family or _guess_font(asset.palette)
                existing.indexed_at = datetime.utcnow()
                await self.session.flush()
                report.assets_updated += 1
                report.inserted_ids.append(str(existing.id))
                # Re-embed
                await ensure_embedding_for_asset(self.session, existing)
            else:
                row = SlideAsset(
                    id=uuid.uuid4(),
                    source_sample_id=None,
                    page_index=asset.slide_index,
                    visual_type=classification.visual_type,
                    title=classification.title,
                    body_text=asset.text or None,
                    color_palette=asset.palette,
                    font_family=_guess_font(asset.palette),
                    industry_tags=classification.industry_tags,
                    thumbnail_path=thumbnail_url,
                    metadata_json=meta,
                    indexed_at=datetime.utcnow(),
                )
                self.session.add(row)
                await self.session.flush()
                report.assets_inserted += 1
                report.inserted_ids.append(str(row.id))
                await ensure_embedding_for_asset(self.session, row)

            # Throttle commits to one per file to avoid pgx noise
        except Exception as e:  # noqa: BLE001
            report.assets_skipped += 1
            report.failures.append(
                f"{asset.source_file}#{asset.slide_index}: {e}"
            )
            logger.error(
                "import_asset_failed",
                file=asset.source_file,
                slide=asset.slide_index,
                error=str(e),
            )

    async def _find_existing(self, asset: ExtractedAsset) -> SlideAsset | None:
        """Look up an existing curated asset by (source_file, page, shape)."""
        # We use metadata_json containment rather than a dedicated column
        # to keep schema changes to zero. The :class:`JSONB` ``@>``
        # operator does an index-friendly containment check on PostgreSQL.
        result = await self.session.execute(
            select(SlideAsset).where(
                SlideAsset.source_sample_id.is_(None),
                SlideAsset.deleted_at.is_(None),
                SlideAsset.metadata_json["curated"].astext == "true",
                SlideAsset.metadata_json["source_file"].astext == asset.source_file,
                SlideAsset.metadata_json["shape_name"].astext == asset.shape_name,
                SlideAsset.page_index == asset.slide_index,
            )
        )
        return result.scalar_one_or_none()


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────


def _guess_font(palette: list[str]) -> str | None:
    """Heuristic font hint based on the dominant palette.

    The user can override per-asset later. We default to Microsoft YaHei
    for the curated library because that's the dominant font across the
    source PPTX set (Chinese consulting style).
    """
    if not palette:
        return None
    # Pick the darkest palette entry as the likely body-text colour
    def _lum(hex_str: str) -> float:
        h = hex_str.lstrip("#")
        if len(h) != 6:
            return 1.0
        r = int(h[0:2], 16) / 255
        g = int(h[2:4], 16) / 255
        b = int(h[4:6], 16) / 255
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    darkest = min(palette, key=_lum)
    if _lum(darkest) < 0.2:
        return "Microsoft YaHei"  # dense, dark text
    return "Microsoft YaHei"


async def import_directory(
    session: AsyncSession,
    directory: str | Path,
    *,
    use_llm: bool = True,
    llm_model: str | None = None,
    dry_run: bool = False,
    max_assets: int | None = None,
    concurrency: int = 4,
) -> ImportReport:
    """Functional wrapper. Use this from the CLI / admin API."""
    importer = CuratedImporter(
        session,
        use_llm=use_llm,
        llm_model=llm_model,
        concurrency=concurrency,
    )
    return await importer.import_directory(
        directory, dry_run=dry_run, max_assets=max_assets
    )


async def drop_curated_assets(session: AsyncSession) -> int:
    """Hard-delete every curated asset row. Used by the admin ``reset`` path."""
    result = await session.execute(
        delete(SlideAsset).where(
            SlideAsset.source_sample_id.is_(None),
            SlideAsset.metadata_json["curated"].astext == "true",
        )
    )
    return result.rowcount or 0
