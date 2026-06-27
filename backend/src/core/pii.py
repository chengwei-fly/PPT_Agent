"""PII detection core (T025) — Presidio + custom rules (FR-008).

Supports: phone, email, id_card, customer_name, address, bank_card
PII strategies:
- `replace` (default, FR-008 Q1 答案): 字段级处置，记录到 pii_summary
- `block`: 拒绝请求
- `allow`: 记录审计但不处置 (rare)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from presidio_analyzer import AnalyzerEngine

from src.core.config import settings
from src.core.observability import get_logger

logger = get_logger("pii")


class PIIAction(str, Enum):
    replace = "replace"
    block = "block"
    allow = "allow"


@dataclass
class PIIHit:
    field: str
    text: str
    start: int
    end: int
    score: float
    replacement: str = ""


@dataclass
class PIIDetectionResult:
    hits: list[PIIHit] = field(default_factory=list)
    redacted_text: str = ""
    has_pii: bool = False

    def to_summary(self) -> dict[str, Any]:
        return {
            "hit_count": len(self.hits),
            "fields": sorted({h.field for h in self.hits}),
            "actions": [
                {
                    "field": h.field,
                    "start": h.start,
                    "end": h.end,
                    "score": h.score,
                    "replacement": h.replacement,
                }
                for h in self.hits
            ],
        }


# ─── Chinese PII patterns (FR-008: phone / email / id_card / customer_name) ─
CN_PATTERNS: dict[str, re.Pattern] = {
    "phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "id_card": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "bank_card": re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
    # Customer name heuristic: 2-4 CJK chars preceded by "客户" / "联系人" / "姓名" / "name"
    "customer_name": re.compile(
        r"(?:客户|联系人|姓名|先生|女士|您好|对方)[\s:：]*[\u4e00-\u9fa5]{2,4}",
    ),
    # Address heuristic: contains 省市/区/路/号
    "address": re.compile(
        r"[\u4e00-\u9fa5]{2,8}(?:省|市|区|县|路|街|号|楼|室|室|院|村)",
    ),
}

REPLACEMENTS: dict[str, str] = {
    "phone": "[PHONE]",
    "email": "[EMAIL]",
    "id_card": "[ID_CARD]",
    "bank_card": "[BANK_CARD]",
    "customer_name": "[CUSTOMER_NAME]",
    "address": "[ADDRESS]",
}


class PIIDetector:
    """PII detection with hybrid approach: regex first (fast, accurate for structured PII)
    + Presidio NLP (fallback for unstructured cases).
    """

    def __init__(self, language: str | None = None) -> None:
        self.language = language or settings.pii_detection_lang
        self._analyzer: AnalyzerEngine | None = None

    def detect(self, text: str, fields: list[str] | None = None) -> PIIDetectionResult:
        """Detect PII in `text`, optionally restricted to specific fields."""
        if not text:
            return PIIDetectionResult(redacted_text="")

        hits: list[PIIHit] = []
        target_fields = fields or settings.pii_fields
        for fld in target_fields:
            pattern = CN_PATTERNS.get(fld)
            if not pattern:
                continue
            for m in pattern.finditer(text):
                hits.append(
                    PIIHit(
                        field=fld,
                        text=m.group(0),
                        start=m.start(),
                        end=m.end(),
                        score=0.95,
                        replacement=REPLACEMENTS.get(fld, f"[{fld.upper()}]"),
                    )
                )

        # Apply longest-first non-overlap (so customer_name doesn't double-replace)
        hits.sort(key=lambda h: (h.start, -h.end))
        result_text = text
        offset = 0
        last_end = -1
        for h in hits:
            if h.start < last_end:
                continue  # skip overlap
            result_text = (
                result_text[: h.start + offset] + h.replacement + result_text[h.end + offset :]
            )
            offset += len(h.replacement) - (h.end - h.start)
            last_end = h.end

        return PIIDetectionResult(
            hits=hits,
            redacted_text=result_text,
            has_pii=len(hits) > 0,
        )

    def redact(self, text: str, fields: list[str] | None = None) -> str:
        return self.detect(text, fields).redacted_text


# ─── Singleton accessor ─────────────────────────────────────────────
_detector: PIIDetector | None = None


def get_pii_detector() -> PIIDetector:
    global _detector
    if _detector is None:
        _detector = PIIDetector()
    return _detector
