"""ORM model package — single import surface.

Importing this package ensures all models are registered on Base.metadata
so Alembic autogenerate sees them.
"""

from src.db.models.api_key import ApiKey
from src.db.models.credential import Credential
from src.db.models.draft import (
    Draft,
    DraftExportJob,
    DraftSlide,
    DraftSlideSourceType,
    MaterialSearchIndex,
)
from src.db.models.embedding import Embedding
from src.db.models.generation_task import GenerationMode, GenerationTask, TaskStage, TaskStatus
from src.db.models.idempotency import IdempotencyKey
from src.db.models.parse_result import ParseResult
from src.db.models.preference import Preference, PreferenceScope
from src.db.models.sample import FileType, ParseStatus, Sample
from src.db.models.security_event import SecurityAction, SecurityEvent, SecurityEventType
from src.db.models.slide_asset import SlideAsset, SlideVisualType
from src.db.models.trace_stage import StageStatus, TraceStage
from src.db.models.user import User, UserTier

__all__ = [
    "ApiKey",
    "Credential",
    "Draft",
    "DraftExportJob",
    "DraftSlide",
    "DraftSlideSourceType",
    "Embedding",
    "FileType",
    "GenerationMode",
    "GenerationTask",
    "IdempotencyKey",
    "MaterialSearchIndex",
    "ParseResult",
    "ParseStatus",
    "Preference",
    "PreferenceScope",
    "Sample",
    "SecurityAction",
    "SecurityEvent",
    "SecurityEventType",
    "SlideAsset",
    "SlideVisualType",
    "StageStatus",
    "TaskStage",
    "TaskStatus",
    "TraceStage",
    "User",
    "UserTier",
]
