"""SVG-to-PPTX generation bridge.

Provides the SVG → PPTX conversion pipeline by leveraging the local
generation engine scripts. This module:

  1. Resolves the local scripts directory.
  2. Inserts the scripts path onto `sys.path` (idempotent).
  3. Re-exports the public API: `create_pptx_with_native_svg`,
     `convert_svg_to_slide_shapes`, plus directory helpers.

Usage:
    from src.integrations.svg_pptx_bridge import (
        create_pptx_with_native_svg,
        convert_svg_to_slide_shapes,
        skill_dir,
        references_dir,
    )
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from src.core.observability import get_logger

logger = get_logger("svg_pptx_bridge")

# Repo root = parent of `backend/`.
_THIS_FILE = Path(__file__).resolve()
_BACKEND_DIR = _THIS_FILE.parents[2]  # .../backend
REPO_ROOT = _BACKEND_DIR.parent  # .../PPT_Agent

# Generation engine paths — configurable via environment variables.
# Set PPTAGENT_ENGINE_ROOT to the root of the SVG-to-PPTX generation engine.
_GENERATION_ROOT = Path(os.environ.get("PPTAGENT_ENGINE_ROOT", ""))
_GENERATION_SCRIPTS = Path(os.environ.get("PPTAGENT_ENGINE_SCRIPTS", ""))
_GENERATION_REFERENCES = Path(os.environ.get("PPTAGENT_ENGINE_REFERENCES", ""))
_GENERATION_TEMPLATES = Path(os.environ.get("PPTAGENT_ENGINE_TEMPLATES", ""))


@lru_cache(maxsize=1)
def _ensure_path() -> Path:
    """Insert generation scripts dir on sys.path (idempotent)."""
    if not _GENERATION_SCRIPTS.is_dir():
        raise RuntimeError(
            f"Generation scripts not found at {_GENERATION_SCRIPTS}.",
        )
    pstr = str(_GENERATION_SCRIPTS)
    if pstr not in sys.path:
        sys.path.insert(0, pstr)
        logger.info("generation_scripts_on_sys_path", path=pstr)
    return _GENERATION_SCRIPTS


@lru_cache(maxsize=1)
def _load_svg_to_pptx():
    """Import `svg_to_pptx` from the local generation scripts."""
    _ensure_path()
    import svg_to_pptx  # type: ignore[import-not-found]

    missing = [
        n
        for n in ("create_pptx_with_native_svg", "convert_svg_to_slide_shapes")
        if not hasattr(svg_to_pptx, n)
    ]
    if missing:
        raise RuntimeError(
            f"Local svg_to_pptx module is missing expected API: {missing}",
        )
    return svg_to_pptx


# Public re-exports ----------------------------------------------------------


def create_pptx_with_native_svg(*args, **kwargs):
    """Convert SVG files to a native PPTX presentation."""
    return _load_svg_to_pptx().create_pptx_with_native_svg(*args, **kwargs)


def convert_svg_to_slide_shapes(*args, **kwargs):
    """Convert SVG content into PPTX slide shapes."""
    return _load_svg_to_pptx().convert_svg_to_slide_shapes(*args, **kwargs)


@lru_cache(maxsize=1)
def skill_dir() -> Path:
    """Return the absolute path to the generation skill directory."""
    return _GENERATION_ROOT


@lru_cache(maxsize=1)
def references_dir() -> Path:
    """Return the absolute path to the references directory."""
    _ensure_path()
    return _GENERATION_REFERENCES


@lru_cache(maxsize=1)
def templates_dir() -> Path:
    """Return the absolute path to the templates directory."""
    return _GENERATION_TEMPLATES


def health_check() -> dict:
    """Return diagnostic info about the local generation engine install."""
    return {
        "repo_root": str(REPO_ROOT),
        "generation_root_exists": _GENERATION_ROOT.is_dir(),
        "scripts_on_path": str(_GENERATION_SCRIPTS) in sys.path,
        "skill_md_exists": (skill_dir() / "SKILL.md").is_file(),
        "references_dir_exists": _GENERATION_REFERENCES.is_dir(),
        "templates_dir_exists": _GENERATION_TEMPLATES.is_dir(),
    }


# Eagerly validate at import time (so misconfiguration fails fast).
try:
    if os.environ.get("PPTAGENT_SKIP_INTEGRATION_CHECK") != "1":
        _ensure_path()
except RuntimeError as e:
    logger.warning("svg_pptx_bridge_not_ready", error=str(e))


__all__ = [
    "REPO_ROOT",
    "convert_svg_to_slide_shapes",
    "create_pptx_with_native_svg",
    "health_check",
    "references_dir",
    "skill_dir",
    "templates_dir",
]
