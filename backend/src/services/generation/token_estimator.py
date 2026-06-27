"""Token estimator (FR-004 / T041).

Uses historical median tokens-per-page for similar prompt length / sample count.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

# Historical medians (empirical baselines for 1536-d embeddings + gpt-4o-mini):
# - outline stage:    ~150 tokens per slide
# - points stage:     ~300 tokens per slide
# - svg stage:        ~600 tokens per slide
# - pptx stage:       ~50 tokens (no LLM)
# Plus fixed overhead: ~500 tokens (system prompt, retrieval, tool calls)
TOKENS_PER_SLIDE_BY_STAGE: dict[str, int] = {
    "outline": 150,
    "points": 300,
    "svg": 600,
    "pptx": 50,
}
# General mode: LLM generates full SVG per slide (much larger output)
TOKENS_PER_SLIDE_GENERAL: dict[str, int] = {
    "outline": 500,
    "points": 800,
    "svg": 4000,
    "pptx": 50,
}
BASE_OVERHEAD_TOKENS = 500
SECONDS_PER_TOKEN = 0.02  # empirical ~50 tok/s on gpt-4o-mini
DEFAULT_PAGES = 10
SAMPLE_CONTEXT_TOKENS = 400  # per-sample context budget


@dataclass
class Estimate:
    tokens: int
    seconds: int


def estimate_generation(
    prompt: str,
    sample_count: int = 0,
    pages: int = DEFAULT_PAGES,
    mode: str = "knowledge_base",
) -> Estimate:
    """Estimate total tokens + seconds for a generation task."""
    per_slide = TOKENS_PER_SLIDE_GENERAL if mode == "general" else TOKENS_PER_SLIDE_BY_STAGE
    total = BASE_OVERHEAD_TOKENS + sum(per_slide[stage] * pages for stage in per_slide)
    total += SAMPLE_CONTEXT_TOKENS * sample_count
    # Add some buffer for retries
    total = int(total * 1.2)
    seconds = max(30, int(total * SECONDS_PER_TOKEN))
    return Estimate(tokens=total, seconds=seconds)


def median_estimate(history: list[int]) -> int:
    if not history:
        return BASE_OVERHEAD_TOKENS
    return int(statistics.median(history))
