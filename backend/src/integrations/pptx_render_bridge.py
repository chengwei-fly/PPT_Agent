"""PPTX render bridge.

Bridges the internal SVG-to-PPTX rendering library that lives at
``backend/src/integrations/ppt_engine/``. The library is bundled inside
the repository so the project is self-contained and deploys without
needing any external skill install. Operators can still override the
location through these environment variables:

- ``PPTAGENT_RENDERER_ROOT``         (renderer root: contains scripts/ and references/)
- ``PPTAGENT_RENDERER_SCRIPTS``      (overrides ``<root>/scripts``)
- ``PPTAGENT_RENDERER_REFERENCES``   (overrides ``<root>/references``)
- ``PPTAGENT_RENDERER_TEMPLATES``    (overrides ``<root>/templates`` — optional)

This module:
  1. Resolves the renderer root (env var or bundled default).
  2. Inserts the scripts dir onto ``sys.path`` (idempotent).
  3. Re-exports the public API: ``create_pptx_with_native_svg`` and
     ``convert_svg_to_slide_shapes``.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from src.core.observability import get_logger

logger = get_logger("pptx_render_bridge")

# Repo root = parent of `backend/`.
_THIS_FILE = Path(__file__).resolve()
_INTEGRATIONS_DIR = _THIS_FILE.parent  # .../backend/src/integrations
_BACKEND_DIR = _INTEGRATIONS_DIR.parent  # .../backend
REPO_ROOT = _BACKEND_DIR.parent  # .../PPT_Agent

# Default bundled renderer (ships with the repo, no extra setup required).
_BUNDLED_RENDERER_ROOT = _INTEGRATIONS_DIR / "ppt_engine"
_BUNDLED_SCRIPTS = _BUNDLED_RENDERER_ROOT / "scripts"
_BUNDLED_REFERENCES = _BUNDLED_RENDERER_ROOT / "references"
_BUNDLED_TEMPLATES = _BUNDLED_RENDERER_ROOT / "templates"  # optional, may not exist


@lru_cache(maxsize=1)
def _renderer_root() -> Path:
    return Path(os.environ.get("PPTAGENT_RENDERER_ROOT", str(_BUNDLED_RENDERER_ROOT)))


@lru_cache(maxsize=1)
def _renderer_scripts() -> Path:
    override = os.environ.get("PPTAGENT_RENDERER_SCRIPTS")
    if override:
        return Path(override)
    root = _renderer_root()
    candidate = root / "scripts"
    return candidate if candidate.is_dir() else _BUNDLED_SCRIPTS


@lru_cache(maxsize=1)
def _renderer_references() -> Path:
    override = os.environ.get("PPTAGENT_RENDERER_REFERENCES")
    if override:
        return Path(override)
    root = _renderer_root()
    candidate = root / "references"
    return candidate if candidate.is_dir() else _BUNDLED_REFERENCES


@lru_cache(maxsize=1)
def _renderer_templates() -> Path:
    override = os.environ.get("PPTAGENT_RENDERER_TEMPLATES")
    if override:
        return Path(override)
    root = _renderer_root()
    candidate = root / "templates"
    return candidate if candidate.is_dir() else _BUNDLED_TEMPLATES


@lru_cache(maxsize=1)
def _ensure_path() -> Path:
    """Insert renderer scripts dir on sys.path (idempotent)."""
    scripts_dir = _renderer_scripts()
    if not scripts_dir.is_dir():
        raise RuntimeError(
            f"Renderer scripts not found at {scripts_dir}. "
            "Set PPTAGENT_RENDERER_SCRIPTS or restore the bundled "
            "renderer under backend/src/integrations/ppt_engine/scripts/."
        )
    pstr = str(scripts_dir)
    if pstr not in sys.path:
        sys.path.insert(0, pstr)
        logger.info("renderer_scripts_on_sys_path", path=pstr)
    return scripts_dir


@lru_cache(maxsize=1)
def _load_pptx_renderer():
    """Import `pptx_renderer` from the bundled rendering library."""
    _ensure_path()
    import pptx_renderer  # type: ignore[import-not-found]

    missing = [
        n
        for n in ("create_pptx_with_native_svg", "convert_svg_to_slide_shapes")
        if not hasattr(pptx_renderer, n)
    ]
    if missing:
        raise RuntimeError(
            f"Local pptx_renderer module is missing expected API: {missing}",
        )
    return pptx_renderer


# Public re-exports ----------------------------------------------------------


def create_pptx_with_native_svg(*args, **kwargs):
    """Convert SVG files to a native PPTX presentation."""
    return _load_pptx_renderer().create_pptx_with_native_svg(*args, **kwargs)


def convert_svg_to_slide_shapes(*args, **kwargs):
    """Convert SVG content into PPTX slide shapes."""
    return _load_pptx_renderer().convert_svg_to_slide_shapes(*args, **kwargs)


@lru_cache(maxsize=1)
def skill_dir() -> Path:
    """Return the absolute path to the rendering library's skill root."""
    return _renderer_root()


@lru_cache(maxsize=1)
def references_dir() -> Path:
    """Return the absolute path to the references directory."""
    return _renderer_references()


@lru_cache(maxsize=1)
def templates_dir() -> Path:
    """Return the absolute path to the templates directory."""
    return _renderer_templates()


def health_check() -> dict:
    """Return diagnostic info about the bundled rendering library install."""
    return {
        "repo_root": str(REPO_ROOT),
        "bundled_renderer_root": str(_BUNDLED_RENDERER_ROOT),
        "renderer_root": str(_renderer_root()),
        "renderer_root_exists": _renderer_root().is_dir(),
        "scripts_on_path": str(_renderer_scripts()) in sys.path,
        "skill_md_exists": (skill_dir() / "SKILL.md").is_file(),
        "references_dir_exists": references_dir().is_dir(),
        "templates_dir_exists": templates_dir().is_dir(),
    }


# Eagerly validate at import time (so misconfiguration fails fast).
try:
    if os.environ.get("PPTAGENT_SKIP_INTEGRATION_CHECK") != "1":
        _ensure_path()
except RuntimeError as e:
    logger.warning("pptx_render_bridge_not_ready", error=str(e))


__all__ = [
    "REPO_ROOT",
    "convert_svg_to_slide_shapes",
    "create_pptx_with_native_svg",
    "health_check",
    "references_dir",
    "skill_dir",
    "templates_dir",
]
