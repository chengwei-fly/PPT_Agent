"""DEPRECATED — legacy ReActAgent wrapper (M-evolve: superseded by OrchestratorAgent).

⚠ This module is the LEGACY ReAct wrapper and is NO LONGER the
production code path. It is kept here only for back-compat with
test fixtures / external scripts that still import ``ReActAgent``
from ``src.agents.react_agent``.

The new ReAct-driven orchestrator lives in
``src.agents.orchestrator.OrchestratorAgent`` (which delegates the
inner ReAct loop to ``src.integrations.agentscope_compat.ReActAgent``)
and is invoked by ``src.scheduler.worker.process_generation_task``.

This file is now a thin re-export shim. New work should target
``src.agents.orchestrator.OrchestratorAgent`` directly.
"""

from __future__ import annotations

import warnings

from src.integrations.agentscope_compat import (
    AGENTSCOPE_AVAILABLE,
    ReActAgent as _CompatReActAgent,
)
from src.integrations.agentscope_compat import Tool as _CompatTool

warnings.warn(
    "src.agents.react_agent.ReActAgent is deprecated; use "
    "src.agents.orchestrator.OrchestratorAgent instead.",
    DeprecationWarning,
    stacklevel=2,
)


class ReActAgent:  # pragma: no cover - legacy shim
    """Deprecated. Use :class:`src.agents.orchestrator.OrchestratorAgent`."""

    def __init__(self, owner_id) -> None:
        warnings.warn(
            "ReActAgent from src.agents.react_agent is deprecated. "
            "The new ReAct orchestrator is "
            "src.agents.orchestrator.OrchestratorAgent.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.owner_id = owner_id
        # No-op compatibility: preserve attribute access patterns of the
        # old API so external imports don't crash, but route to the
        # new compat ReActAgent underneath. No tools are registered.
        self._react = _CompatReActAgent(name="pptagent_react_legacy", tools=[])

    async def run(self, prompt: str, **kwargs):  # pragma: no cover - legacy
        return await self._react.invoke(prompt, **kwargs)

    @property
    def trace(self):  # pragma: no cover - legacy
        return self._react.trace


__all__ = ["ReActAgent", "AGENTSCOPE_AVAILABLE"]
