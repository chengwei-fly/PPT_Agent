"""Curated material library importer (US6 / System-Curated extension).

This package ingests PPT/PPTX files from a directory and produces
``slide_assets`` rows that are visible to ALL users (``source_sample_id = NULL``,
``metadata_json.curated = true``). Designed for the team's shared icon /
template / diagram library — the kind of content users previously had to
re-attach from a personal PPT every time.

The pipeline:

    PPTX ─► Extractor (per-slide images + text) ─► Classifier (LLM or heuristic)
                                                   │
                                                   ▼
                                            SlideAsset rows
                                          + MinIO thumbnails

Designed to be:

* **DB-agnostic** at the extractor layer (works on raw PPTX bytes)
* **LLM-optional** — falls back to deterministic heuristic classification
  when no ``OPENAI_API_KEY`` (or compatible) is configured
* **Idempotent** — re-running over the same directory drops and re-creates
  curated assets whose ``source_file`` matches
"""

from src.services.material_importer.classifier import (
    HeuristicClassifier,
    LLMClassifier,
    MaterialClassifier,
    classify_asset,
)
from src.services.material_importer.extractor import (
    ExtractedAsset,
    PPTXExtractor,
    extract_from_file,
)
from src.services.material_importer.importer import (
    CuratedImporter,
    ImportReport,
    import_directory,
)

__all__ = [
    "PPTXExtractor",
    "ExtractedAsset",
    "extract_from_file",
    "MaterialClassifier",
    "HeuristicClassifier",
    "LLMClassifier",
    "classify_asset",
    "CuratedImporter",
    "ImportReport",
    "import_directory",
]
