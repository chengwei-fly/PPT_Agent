"""PII middleware — registers PII detection in agent middleware chain (T025 + spec Q1).

Field-level replace per FR-008: PII text → tagged placeholder, original chunk index preserved.
"""

from __future__ import annotations

from src.core.observability import get_logger
from src.core.pii import get_pii_detector

logger = get_logger("pii_middleware")


class PIIMiddleware:
    """Intercepts text inputs/outputs and redacts PII per FR-008."""

    def __init__(self) -> None:
        self._detector = get_pii_detector()

    async def pre_invoke(self, prompt: str, **context) -> dict:
        """Scan + redact PII in user prompt before sending to LLM."""
        result = self._detector.detect(prompt)
        if result.has_pii:
            logger.info(
                "pii_detected",
                field_count=len({h.field for h in result.hits}),
                hit_count=len(result.hits),
            )
        return {
            "redacted_prompt": result.redacted_text,
            "pii_summary": result.to_summary(),
        }

    async def post_invoke(self, response: str, **context) -> dict:
        """Sanitize LLM output for PII leakage."""
        result = self._detector.detect(response)
        return {
            "redacted_response": result.redacted_text,
            "pii_summary": result.to_summary(),
        }
