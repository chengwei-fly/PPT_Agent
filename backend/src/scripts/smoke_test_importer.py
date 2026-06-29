"""Local smoke test for the curated importer extractor + classifier.

This script does NOT need PostgreSQL, MinIO, Redis, or an LLM key. It
exercises the PPTX → per-slide image extraction and the deterministic
heuristic classifier, and writes the resulting thumbnails to a local
directory for visual inspection.

Usage:
    uv run python -m src.scripts.smoke_test_importer --src "F:/PPT素材" --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.services.material_importer.classifier import (  # noqa: E402
    HeuristicClassifier,
    classify_asset,
)
from src.services.material_importer.extractor import (  # noqa: E402
    discover_pptx_files,
    extract_from_file,
)


async def _amain(args: argparse.Namespace) -> int:
    src = Path(args.src)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    files = list(discover_pptx_files(src))
    if args.limit:
        files = files[: args.limit]
    if not files:
        print(f"ERROR: no PPT/PPTX files found under {src}", file=sys.stderr)
        return 2

    summary = []
    total = 0
    for path in files:
        print(f"\n=== {path.name} ===")
        try:
            assets = extract_from_file(path)
        except Exception as e:  # noqa: BLE001
            print(f"  extract failed: {e}")
            continue
        print(f"  extracted: {len(assets)} asset(s)")
        for a in assets:
            # Classify
            try:
                cls = await classify_asset(a, prefer_llm=False)
            except Exception as e:  # noqa: BLE001
                print(f"  classify failed: {e}")
                cls = None
            # Persist thumbnail locally
            thumb_path = out / f"{path.stem}__s{a.slide_index:03d}__{a.shape_name.replace(' ', '_')}.jpg"
            thumb_path.write_bytes(a.image_bytes)
            tags = ",".join(cls.industry_tags) if cls else ""
            vt = cls.visual_type.value if cls else "?"
            print(
                f"  slide {a.slide_index:>3} | {a.width:>4}x{a.height:<4} "
                f"| vt={vt:<12} | tags=[{tags}] | {thumb_path.name}"
            )
            if cls and cls.title:
                print(f"      title: {cls.title}")
            total += 1
            summary.append(
                {
                    "file": path.name,
                    "slide": a.slide_index,
                    "shape": a.shape_name,
                    "ext": a.image_ext,
                    "width": a.width,
                    "height": a.height,
                    "vt": vt,
                    "title": cls.title if cls else None,
                    "tags": cls.industry_tags if cls else [],
                    "used": cls.used if cls else "error",
                    "thumb": str(thumb_path.relative_to(out)),
                }
            )

    if args.json:
        (out / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nSummary written to {out / 'summary.json'}")
    print(f"\nTotal assets processed: {total}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True, help="Directory of PPT/PPTX files")
    p.add_argument(
        "--out",
        default="./_smoke_output",
        help="Where to write thumbnails (default: ./_smoke_output)",
    )
    p.add_argument("--limit", type=int, default=0, help="Max number of files to process")
    p.add_argument("--json", action="store_true", help="Write summary.json")
    args = p.parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
