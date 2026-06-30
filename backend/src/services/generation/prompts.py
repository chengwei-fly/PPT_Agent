"""System prompt templates for the ReAct agent.

These templates are LITERAL — they MUST NOT change between
generations of the same task (so the LLM sees consistent
grounding). Each template exposes a ``render(**kwargs)`` method.

Templates were previously rebuilt on every LLM call inside
``pipeline._stage_svg_general`` (5.5k tokens rebuilt per slide).
Centralising them here lets the agent cache the rendered text
per (style, mode) tuple and reuse across the whole batch.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from src.services.generation.reference_loader import ReferenceLoader

# Maximum number of characters we include from each reference
# doc — large enough to ground the LLM, small enough to keep
# per-call context bounded.
_MAX_SHARED_STANDARDS_CHARS = 3000
_MAX_VISUAL_STYLE_CHARS = 2000
_MAX_COMMUNICATION_MODE_CHARS = 2000


@dataclass(frozen=True)
class _SystemPromptKey:
    visual_style: str | None
    communication_mode: str | None

    def cache_key(self) -> str:
        return f"{self.visual_style or ''}::{self.communication_mode or ''}"


_SYSTEM_PROMPT_CACHE: dict[str, str] = {}


def _build_svg_system_prompt(
    *,
    visual_style: str | None,
    communication_mode: str | None,
    refs: ReferenceLoader,
) -> str:
    """Build the canonical SVG-rendering system prompt (cached)."""
    key = _SystemPromptKey(visual_style, communication_mode)
    cache_key = key.cache_key()
    if cache_key in _SYSTEM_PROMPT_CACHE:
        return _SYSTEM_PROMPT_CACHE[cache_key]

    parts: list[str] = [
        "You are an expert SVG designer for PowerPoint presentations.",
        "Generate clean, well-structured SVG markup for slides.",
        "Canvas: viewBox='0 0 1280 720' (16:9 aspect ratio).",
        "Output ONLY the SVG markup, no markdown fences, no explanation.",
        "",
        "## Critical Rules (from shared standards)",
        "Banned SVG features: mask, <style>, class, external CSS, <foreignObject>,",
        "<symbol>+<use>, textPath, @font-face, <animate*>, <script>, <iframe>.",
        "Text must use raw Unicode. Use XML entities for & < >.",
        "Group related elements with <g>.",
    ]
    shared = refs.load_shared_standards()
    if shared:
        parts.append(
            f"\n## Shared Standards (excerpt)\n{shared[:_MAX_SHARED_STANDARDS_CHARS]}"
        )
    if visual_style:
        style_spec = refs.load_visual_style(visual_style)
        if style_spec:
            parts.append(
                f"\n## Visual Style: {visual_style}\n{style_spec[:_MAX_VISUAL_STYLE_CHARS]}"
            )
    if communication_mode:
        mode_spec = refs.load_communication_mode(communication_mode)
        if mode_spec:
            parts.append(
                f"\n## Communication Mode: {communication_mode}\n{mode_spec[:_MAX_COMMUNICATION_MODE_CHARS]}"
            )

    rendered = "\n".join(parts)
    _SYSTEM_PROMPT_CACHE[cache_key] = rendered
    return rendered


def get_svg_system_prompt(visual_style: str | None, communication_mode: str | None) -> str:
    """Return the cached SVG system prompt for the given style+mode.

    Safe to call from multiple concurrent tasks — the cache is keyed
    on (style, mode) and rendered once per pair.
    """
    return _build_svg_system_prompt(
        visual_style=visual_style,
        communication_mode=communication_mode,
        refs=ReferenceLoader(),
    )


def clear_cache() -> None:
    """Drop the system-prompt cache (used by tests / hot-reload)."""
    _SYSTEM_PROMPT_CACHE.clear()


def prompt_hash(visual_style: str | None, communication_mode: str | None) -> str:
    """Stable hash of the rendered prompt — useful for cache invalidation."""
    return hashlib.sha256(
        get_svg_system_prompt(visual_style, communication_mode).encode("utf-8")
    ).hexdigest()[:16]
