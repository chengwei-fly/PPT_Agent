"""CLI entry point — import a directory of PPTX files into the curated
material library.

Usage:

    # Local dev (heuristic classification, no LLM key needed)
    uv run python -m src.scripts.import_material_library \\
        --src "F:/PPT素材"

    # With LLM (multimodal classification)
    uv run python -m src.scripts.import_material_library \\
        --src "F:/PPT素材" --use-llm --llm-model qwen-vl-max

    # Dry-run — extract + classify but do not write to DB
    uv run python -m src.scripts.import_material_library \\
        --src "F:/PPT素材" --dry-run --max-assets 20

The CLI initialises DB + MinIO through the same hooks the API uses, then
delegates to :func:`import_directory`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Make `src` importable when invoked as ``python -m src.scripts....`` from
# inside ``backend/``.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.core.lifespan import (  # noqa: E402
    init_db,
    init_redis,
    init_minio,
    dispose_db,
)
from src.core.observability import configure_observability  # noqa: E402
from src.db.session import get_session_factory  # noqa: E402
from src.services.material_importer.importer import (  # noqa: E402
    CuratedImporter,
    import_directory,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="import_material_library",
        description=(
            "Ingest a directory of PPT/PPTX files into the curated material "
            "library (system-wide, visible to all users)."
        ),
    )
    p.add_argument(
        "--src",
        required=True,
        help="Root directory containing PPT/PPTX files (searched recursively).",
    )
    p.add_argument(
        "--use-llm",
        action="store_true",
        help=(
            "Use a multimodal LLM (OpenAI-compatible) for visual_type and "
            "industry_tags. Falls back to heuristic when no key is set."
        ),
    )
    p.add_argument(
        "--llm-model",
        default=None,
        help="Override the multimodal model (e.g. qwen-vl-max, gpt-4o-mini).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract + classify but do not write to the database.",
    )
    p.add_argument(
        "--max-assets",
        type=int,
        default=None,
        help="Hard cap on assets imported (for testing).",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Max concurrent LLM calls when classifying.",
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help=(
            "DESTRUCTIVE: hard-delete all existing curated assets before "
            "importing. Useful when you want to start from a clean slate."
        ),
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print the final report as a JSON object (else a short summary).",
    )
    return p


async def _amain(args: argparse.Namespace) -> int:
    src_path = Path(args.src)
    if not src_path.exists():
        print(f"ERROR: source path not found: {src_path}", file=sys.stderr)
        return 2
    if not src_path.is_dir():
        print(f"ERROR: --src must be a directory: {src_path}", file=sys.stderr)
        return 2

    configure_observability(None)  # logger only — no app context

    print(">> Initialising database + storage…")
    await init_db()
    # Redis is only used by the generation queue — we tolerate its absence
    # so the importer can run on a stripped-down environment.
    try:
        from src.scheduler.queue import init_redis

        await init_redis()
        print("   redis: connected")
    except Exception as e:  # noqa: BLE001
        print(f"   redis: SKIPPED ({e})")
    try:
        init_minio()
        print("   minio: connected")
    except Exception as e:  # noqa: BLE001
        print(f"   minio: SKIPPED ({e})")

    factory = get_session_factory()
    try:
        async with factory() as session:
            if args.reset:
                from src.services.material_importer.importer import (
                    drop_curated_assets,
                )

                deleted = await drop_curated_assets(session)
                await session.commit()
                print(f">> Reset: removed {deleted} existing curated asset(s).")

            importer = CuratedImporter(
                session,
                use_llm=args.use_llm,
                llm_model=args.llm_model,
                concurrency=args.concurrency,
            )
            report = await importer.import_directory(
                src_path,
                dry_run=args.dry_run,
                max_assets=args.max_assets,
            )
            if not args.dry_run:
                await session.commit()
    finally:
        await dispose_db()

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_human_summary(report, args)
    return 0


def _print_human_summary(report, args: argparse.Namespace) -> None:
    print()
    print("=" * 60)
    print(f"Curated material import {'(DRY RUN)' if args.dry_run else ''}")
    print("=" * 60)
    print(f"  Files seen:      {report.files_seen}")
    print(f"  Files failed:    {report.files_failed}")
    print(f"  Assets extracted:{report.assets_extracted}")
    print(f"  Inserted:        {report.assets_inserted}")
    print(f"  Updated:         {report.assets_updated}")
    print(f"  Skipped:         {report.assets_skipped}")
    if report.failures:
        print()
        print(f"  First {min(5, len(report.failures))} failures:")
        for f in report.failures[:5]:
            print(f"    - {f}")
    counts = report.classification_counts
    if counts:
        print()
        print("  Classification breakdown:")
        for k in sorted(counts):
            if k.startswith("vt:"):
                continue
            print(f"    {k:<10} : {counts[k]}")
        vt = {k: v for k, v in counts.items() if k.startswith("vt:")}
        if vt:
            print("  visual_type:")
            for k in sorted(vt):
                print(f"    {k[3:]:<14} : {vt[k]}")
    print("=" * 60)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        print("Interrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
