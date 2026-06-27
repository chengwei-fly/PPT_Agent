"""Middleware package — PII / Trace / Behavior / Business.

Registration order (Constitution §V): PII → Trace → Behavior → Business
"""

from src.agents.middleware.behavior_middleware import BehaviorMiddleware
from src.agents.middleware.pii_middleware import PIIMiddleware
from src.agents.middleware.trace_middleware import TraceMiddleware

__all__ = [
    "BehaviorMiddleware",
    "PIIMiddleware",
    "TraceMiddleware",
]
