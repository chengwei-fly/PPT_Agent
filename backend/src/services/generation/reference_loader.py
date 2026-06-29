"""Load visual style and communication mode reference files for LLM context.

Reads visual styles, communication modes, and shared standards from
the generation engine's references/ directory. Caches loaded content
since these files are static (change only on redeployment).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.core.observability import get_logger

logger = get_logger("generation.reference_loader")

# Known visual styles
VISUAL_STYLES = [
    {
        "id": "swiss-minimal",
        "name": "Swiss Minimal",
        "character": "Grid-locked, sharp, aggressive whitespace, no decoration",
        "best_for": "High-end consulting, architecture, type-led",
    },
    {
        "id": "soft-rounded",
        "name": "Soft Rounded",
        "character": "Rounded cards, gentle elevation, approachable",
        "best_for": "Product, SaaS, training, consumer",
    },
    {
        "id": "glassmorphism",
        "name": "Glassmorphism",
        "character": "Translucent glass panels, gradient light, floating depth",
        "best_for": "Modern SaaS, fintech, product launches, AI demos",
    },
    {
        "id": "dark-tech",
        "name": "Dark Tech",
        "character": "Dark canvas, glow accents, geometric precision",
        "best_for": "Tech, AI, data products, launches",
    },
    {
        "id": "blueprint",
        "name": "Blueprint",
        "character": "Schematic line work on dark paper, isometric, annotated",
        "best_for": "Technical briefings, architecture, engineering",
    },
    {
        "id": "editorial",
        "name": "Editorial",
        "character": "Magazine hierarchy, rules & columns, serif/sans interplay",
        "best_for": "Finance, journalism, analysis, explainers",
    },
    {
        "id": "photo-editorial",
        "name": "Photo Editorial",
        "character": "Full-bleed photography dominates, text points & captions",
        "best_for": "Architecture, design, fashion, culture",
    },
    {
        "id": "data-journalism",
        "name": "Data Journalism",
        "character": "Multi-column micro-charts, sidebars, source lines, dense",
        "best_for": "Finance, market reviews, research, data reports",
    },
    {
        "id": "brutalist",
        "name": "Brutalist",
        "character": "Newsprint density, ruled boxes, raw structure, flat",
        "best_for": "Annual reviews, research digests, manifestos",
    },
    {
        "id": "memphis",
        "name": "Memphis",
        "character": "Clashing color blocks, geometric confetti, bold outlines",
        "best_for": "Festivals, consumer, youth, launch hype",
    },
    {
        "id": "zine",
        "name": "Zine",
        "character": "Riso misregistration, halftone, limited palette, print grit",
        "best_for": "Culture, design talks, indie brands",
    },
    {
        "id": "vintage-poster",
        "name": "Vintage Poster",
        "character": "Mid-century flat blocks, halftone, retro-geometric warmth",
        "best_for": "Heritage, hospitality, cultural, anniversaries",
    },
    {
        "id": "paper-cut",
        "name": "Paper Cut",
        "character": "Layered cut-paper sheets, soft inter-layer shadow, tactile",
        "best_for": "Cultural/folk, children, festival, sustainability",
    },
    {
        "id": "sketch-notes",
        "name": "Sketch Notes",
        "character": "Warm paper, doodle line work, soft pastel blocks",
        "best_for": "Education, training, onboarding, knowledge",
    },
    {
        "id": "ink-notes",
        "name": "Ink Notes",
        "character": "Pale field, black hand-ink, sparse semantic accent",
        "best_for": "Methodology, before/after, manifestos",
    },
    {
        "id": "chalkboard",
        "name": "Chalkboard",
        "character": "Dark slate, chalk strokes, powdery pastel accents",
        "best_for": "Teaching, tutorials, classroom, academic",
    },
    {
        "id": "ink-wash",
        "name": "Ink Wash",
        "character": "Rice-paper whitespace, brush marks, seal accent, still",
        "best_for": "Cultural, philosophy, heritage",
    },
    {
        "id": "pixel-art",
        "name": "Pixel Art",
        "character": "Strict pixel grid, blocky forms, limited palette, flat",
        "best_for": "Gaming, retro-tech, nostalgic",
    },
]

# Known communication modes
COMMUNICATION_MODES = [
    {
        "id": "pyramid",
        "name": "Pyramid",
        "narrative_skeleton": "Conclusion first; MECE arguments; every datum carries a comparison",
        "best_for": "Decision support, analysis, strategy, board/exec reports",
    },
    {
        "id": "narrative",
        "name": "Narrative",
        "narrative_skeleton": "Story arc (situation -> tension -> resolution); suspense and turns",
        "best_for": "Pitches, case studies, brand journeys, fundraising",
    },
    {
        "id": "instructional",
        "name": "Instructional",
        "narrative_skeleton": "Concept decomposition; step-by-step; parallel exposition",
        "best_for": "Training, tutorials, explainers, knowledge sharing",
    },
    {
        "id": "showcase",
        "name": "Showcase",
        "narrative_skeleton": "Visual-led impact; big imagery/numbers; emotional rhythm",
        "best_for": "Launches, brand reveals, event/promo decks",
    },
    {
        "id": "briefing",
        "name": "Briefing",
        "narrative_skeleton": "Neutral, complete, scannable; topic titles, even weight, no thesis",
        "best_for": "Status updates, reference decks, catalogs, meeting packs",
    },
]


def _references_dir() -> Path | None:
    """Resolve the references directory."""
    try:
        from src.integrations.pptx_render_bridge import references_dir

        return Path(references_dir())
    except Exception:
        return None


@lru_cache(maxsize=1)
def _load_shared_standards_cached() -> str:
    """Load and cache shared-standards.md content."""
    ref_dir = _references_dir()
    if not ref_dir:
        return ""
    path = ref_dir / "shared-standards.md"
    if not path.exists():
        logger.warning("shared_standards_not_found", path=str(path))
        return ""
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=32)
def _load_visual_style_cached(style_id: str) -> str | None:
    """Load and cache a visual style markdown file."""
    ref_dir = _references_dir()
    if not ref_dir:
        return None
    path = ref_dir / "visual-styles" / f"{style_id}.md"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=16)
def _load_communication_mode_cached(mode_id: str) -> str | None:
    """Load and cache a communication mode markdown file."""
    ref_dir = _references_dir()
    if not ref_dir:
        return None
    path = ref_dir / "modes" / f"{mode_id}.md"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


class ReferenceLoader:
    """Loads reference markdown files for LLM context."""

    def load_shared_standards(self) -> str:
        """Return the full shared-standards.md content (SVG banned features, compatibility rules)."""
        return _load_shared_standards_cached()

    def load_visual_style(self, style_id: str) -> str | None:
        """Return the visual style spec for the given id, or None if not found."""
        return _load_visual_style_cached(style_id)

    def load_communication_mode(self, mode_id: str) -> str | None:
        """Return the communication mode spec for the given id, or None if not found."""
        return _load_communication_mode_cached(mode_id)

    def list_visual_styles(self) -> list[dict[str, str]]:
        """Return all available visual styles with metadata."""
        return VISUAL_STYLES

    def list_communication_modes(self) -> list[dict[str, str]]:
        """Return all available communication modes with metadata."""
        return COMMUNICATION_MODES

    def get_style_ids(self) -> set[str]:
        """Return set of valid visual style IDs."""
        return {s["id"] for s in VISUAL_STYLES}

    def get_mode_ids(self) -> set[str]:
        """Return set of valid communication mode IDs."""
        return {m["id"] for m in COMMUNICATION_MODES}
