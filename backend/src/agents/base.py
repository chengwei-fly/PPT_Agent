"""AgentScope 2.0 base orchestration (T026).

Registers an event bus and exposes a single shared `HarnessAgent` template
for sub-agents to use. Sub-agents (US1 ReActAgent, US3 preference extractor,
US6 material retriever) MUST be wired through this bus.

Constitution §V: All LLM calls MUST go through ReActAgent.invoke()
"""

from __future__ import annotations

from typing import Any

from src.core.observability import get_logger

logger = get_logger("agents")

_bus: Any = None
_initialized = False


async def init_agent_bus() -> None:
    """Initialize the AgentScope event bus + middleware chain.

    Middleware registration order (Constitution §V):
    PII → Trace → Behavior → Business
    """
    global _bus, _initialized
    if _initialized:
        return
    try:
        from agentscope import setup_event_bus  # type: ignore[import-untyped]

        _bus = setup_event_bus()
    except ImportError:
        # AgentScope not installed at runtime; use a simple in-process pub/sub
        _bus = _InMemoryBus()
        logger.warning("agentscope_not_installed — using in-memory event bus")
    _initialized = True
    logger.info("agent_bus_initialized")


def get_agent_bus() -> Any:
    if _bus is None:
        raise RuntimeError("Agent bus not initialized")
    return _bus


# ─── In-process fallback bus (used when agentscope unavailable) ─────
class _InMemoryBus:
    def __init__(self) -> None:
        self._subs: dict[str, list] = {}

    def subscribe(self, topic: str, handler: Any) -> None:
        self._subs.setdefault(topic, []).append(handler)

    def publish(self, topic: str, event: dict[str, Any]) -> None:
        for handler in self._subs.get(topic, []):
            try:
                handler(event)
            except Exception as e:  # pragma: no cover
                logger.error(f"event_handler_error topic={topic}: {e}")


# ─── Re-export commonly used AgentScope types (lazy import) ────────
def get_react_agent_class() -> Any:
    """Lazy load the ReActAgent class so imports don't fail when agentscope missing."""
    from agentscope import ReActAgent  # type: ignore[import-untyped]

    return ReActAgent


def get_harness_agent_class() -> Any:
    """Lazy load the HarnessAgent class."""
    from agentscope import HarnessAgent  # type: ignore[import-untyped]

    return HarnessAgent
