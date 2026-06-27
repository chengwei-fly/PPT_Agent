"""PII detector tool — standalone callable wrapper around src.core.pii."""

from __future__ import annotations

from typing import Any

from src.core.pii import PIIDetectionResult, get_pii_detector


class PIIDetectorTool:
    name = "pii_detector"
    description = (
        "Detect PII (phone, email, id_card, customer_name, address, bank_card) "
        "in arbitrary text. Returns redacted text + structured hit list."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional whitelist of fields to detect",
            },
        },
        "required": ["text"],
    }

    async def func(self, text: str, fields: list[str] | None = None) -> PIIDetectionResult:
        return get_pii_detector().detect(text, fields=fields)
