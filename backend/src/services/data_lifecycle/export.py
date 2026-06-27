"""Data lifecycle — export service (T100 / FR-018)."""

from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile
from datetime import datetime

from sqlalchemy import select

from src.core.observability import get_logger
from src.db.models import (
    GenerationTask,
    ParseResult,
    Preference,
    Sample,
    SecurityAction,
    SecurityEvent,
    SecurityEventType,
)
from src.storage.minio import get_object, put_object

logger = get_logger("data.export")


async def export_user_data(user_id: str) -> str:
    """Package all user data into a ZIP in MinIO; returns job_id."""
    from src.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        # 1. Gather metadata
        samples = (
            await session.execute(select(Sample).where(Sample.owner_id == uuid.UUID(user_id)))
        ).scalars()
        preferences = (
            await session.execute(
                select(Preference).where(Preference.owner_id == uuid.UUID(user_id))
            )
        ).scalars()
        tasks = (
            await session.execute(
                select(GenerationTask).where(GenerationTask.owner_id == uuid.UUID(user_id))
            )
        ).scalars()

        zip_buf = io.BytesIO()
        sha_manifest: dict[str, str] = {}
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # ── manifest.json ─────────────────────────────────────
            manifest = {
                "user_id": user_id,
                "exported_at": datetime.utcnow().isoformat(),
                "format_version": "1.0.0",
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))
            sha_manifest["manifest.json"] = _sha(manifest)

            # ── preferences.json ──────────────────────────────────
            prefs_data = [
                {
                    "id": p.id,
                    "rule_text": p.rule_text,
                    "applies_to": p.applies_to.value,
                    "source_chains": p.source_chains,
                    "apply_count": p.apply_count,
                    "ignore_count": p.ignore_count,
                    "is_active": p.is_active,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in preferences
            ]
            zf.writestr("preferences.json", json.dumps(prefs_data, indent=2, default=str))

            # ── samples/ ─────────────────────────────────────────
            for s in samples:
                # Embed raw file
                try:
                    bucket, key = _parse_path(s.raw_path)
                    raw = get_object(bucket, key)
                    zf.writestr(f"samples/{s.id}/{s.file_name}", raw)
                    sha_manifest[f"samples/{s.id}/{s.file_name}"] = hashlib.sha256(raw).hexdigest()
                except Exception as e:
                    logger.warning("export_sample_failed", sample_id=str(s.id), error=str(e))
                # Embed parse result
                pr = (
                    await session.execute(select(ParseResult).where(ParseResult.sample_id == s.id))
                ).scalar_one_or_none()
                if pr:
                    zf.writestr(
                        f"samples/{s.id}/parse_result.json",
                        json.dumps(pr.structure_json, indent=2, default=str),
                    )

            # ── generation_tasks.json ────────────────────────────
            tasks_data = [
                {
                    "id": str(t.id),
                    "prompt": t.prompt,
                    "status": t.status.value,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "result_pptx_path": t.result_pptx_path,
                    "style_fit_score": t.style_fit_score,
                }
                for t in tasks
            ]
            zf.writestr("generation_tasks.json", json.dumps(tasks_data, indent=2, default=str))

            # ── manifest.sha256 ──────────────────────────────────
            zf.writestr(
                "manifest.sha256",
                "\n".join(f"{sha}  {name}" for name, sha in sorted(sha_manifest.items())),
            )

        data = zip_buf.getvalue()
        job_id = str(uuid.uuid4())
        key = f"exports/{user_id}/{job_id}.zip"
        put_object(
            bucket="ppt-cold",
            key=key,
            data=data,
            content_type="application/zip",
        )

        # Audit event
        session.add(
            SecurityEvent(
                owner_id=uuid.UUID(user_id),
                event_type=SecurityEventType.bulk_export,
                action_taken=SecurityAction.allow,
                related_resource_id=uuid.UUID(job_id),
                details={"size_bytes": len(data), "key": key},
            )
        )
        await session.commit()
        logger.info("user_data_exported", user_id=user_id, job_id=job_id, size=len(data))
        return job_id


def _parse_path(path: str) -> tuple[str, str]:
    if path.startswith("s3://"):
        rest = path[5:]
        bucket, _, key = rest.partition("/")
        return bucket, key
    return "ppt-hot", path


def _sha(obj) -> str:
    s = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
