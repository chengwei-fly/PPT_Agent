"""ReActAgent — LLM-driven content-generation agent.

Inherits from `agentscope.agent.Agent` and registers tools the
LLM can call:

  - `knowledge_retriever` — pull top-k chunks from the user's KB
  - `svg2pptx`            — package SVGs into a final PPTX
"""

from __future__ import annotations

import uuid
from typing import Any

from src.core.observability import get_logger
from src.integrations.agentscope_compat import (
    AGENTSCOPE_AVAILABLE,
    Tool,
)
from src.integrations.agentscope_compat import (
    ReActAgent as _BaseReActAgent,
)
from src.tools.knowledge_retriever import KnowledgeRetriever
from src.tools.svg2pptx import SVG2PPTXTool

logger = get_logger("react_agent")


class ReActAgent:
    """PPTagent's LLM-driven content-generation agent.

    This is a thin wrapper that:

      1. Owns the underlying AgentScope ReActAgent (inherits from
         `agentscope.agent.Agent` via `agentscope_compat`).
      2. Registers the four content-stage tools.
      3. Exposes a stable PPTagent-facing API (`run`, `set_retrieval`)
         that the orchestrator and tests use.
    """

    def __init__(self, owner_id: uuid.UUID) -> None:
        self.owner_id = owner_id
        self._kb = KnowledgeRetriever(owner_id=owner_id)
        self._svg2pptx = SVG2PPTXTool()

        # Build the AgentScope ReActAgent. If the local AgentScope
        # import failed, `_BaseReActAgent.__init__` raises an
        # actionable error directing the user to run
        # `install_local_deps.sh`.
        self._react = _BaseReActAgent(
            name="pptagent_react",
            tools=[
                Tool(
                    name="knowledge_retriever",
                    description=(
                        "Pull top-k relevant chunks from the user's "
                        "knowledge base for the current prompt."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "top_k": {"type": "integer", "default": 5},
                        },
                        "required": ["query"],
                    },
                    func=self._kb.retrieve_async,
                ),
                Tool(
                    name="svg2pptx",
                    description=(
                        "Package a list of slide SVGs into a final PPTX. "
                        "Converts SVG slides to PPTX format."
                    ),
                    parameters=self._svg2pptx.parameters,
                    func=self._svg2pptx.func,
                ),
            ],
        )
        if AGENTSCOPE_AVAILABLE:
            logger.info(
                "react_agent_built_on_local_agentscope",
                tools=list(self._react.tools),
            )

    @property
    def agentscope_agent(self) -> _BaseReActAgent:
        """Direct access to the underlying AgentScope ReActAgent.

        Useful for tests and for advanced wiring (custom model
        callable, custom middleware, etc.).
        """
        return self._react

    async def run(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Run the ReAct loop and return the result + trace."""
        return await self._react.invoke(prompt, **kwargs)

    # ── Convenience pass-throughs used by the orchestrator ─────────
    async def retrieve(self, query: str, top_k: int = 5) -> list[Any]:
        return await self._kb.retrieve_async(query=query, top_k=top_k)

    def set_retrieval(self, hits: list[Any]) -> None:
        """Compatibility shim — the orchestrator pre-fetches hits
        and shoves them onto the agent."""
        self._last_retrieval = hits

    @property
    def trace(self) -> list[dict[str, Any]]:
        return self._react.trace


__all__ = ["ReActAgent"]
