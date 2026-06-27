"""AgentScope compatibility shim (Constitution §I).

The local AgentScope sibling repo at `f:/workspace/PPT_Agent/AgentScope`
exposes:

  - `agentscope.agent.Agent`              — base class for any agent
  - `agentscope.agent.ContextConfig`      — context-window config
  - `agentscope.agent.ModelConfig`        — model config
  - `agentscope.agent.ReActConfig`        — ReAct-loop config
  - `agentscope.logger` / `setup_logger`  — structured logging

It does **not** ship a ready-made `ReActAgent` or `HarnessAgent` class.
The PPTagent design (plan.md §3.2, Constitution §I) calls for both,
so we implement them here on top of `AgentScope`'s base class. The
implementation follows the AgentScope pattern: an agent owns a list
of tools (callables with JSON schemas) and a `__call__`/`invoke`
entry point; tool selection is done by an LLM in ReAct mode, or by
a fixed harness in Harness mode.

Public surface:
    from src.integrations.agentscope_compat import (
        Agent,            # the upstream AgentScope base class
        ReActConfig,
        ModelConfig,
        ReActAgent,       # PPTagent's ReAct-loop agent
        HarnessAgent,     # PPTagent's fixed-pipeline harness agent
        get_agentscope_version,
    )
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from src.core.observability import get_logger

logger = get_logger("agentscope_compat")

# Real AgentScope — installed in editable mode from the sibling repo
# at `f:/workspace/PPT_Agent/AgentScope/`. If the editable install
# hasn't been run yet, fail loudly with an actionable message.
try:
    from agentscope import __version__ as _AGENTSCOPE_VERSION  # type: ignore
    from agentscope.agent import (  # type: ignore
        Agent as _AgentScopeAgent,
    )
    from agentscope.agent import (
        ContextConfig,
        ModelConfig,
        ReActConfig,
    )

    AGENTSCOPE_AVAILABLE = True
except ImportError as e:  # pragma: no cover - actionable error path
    AGENTSCOPE_AVAILABLE = False
    _IMPORT_ERROR = e
    _AGENTSCOPE_VERSION = "unknown"

    class _AgentScopeAgent:  # type: ignore[no-redef]
        """Placeholder so `Agent` is always defined for type imports."""

        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "AgentScope is not importable. Did you run "
                "`bash backend/scripts/install_local_deps.sh` to install "
                "the sibling `f:/workspace/PPT_Agent/AgentScope` repo in "
                "editable mode? Original import error: "
                f"{_IMPORT_ERROR}",
            )


Agent = _AgentScopeAgent


def get_agentscope_version() -> str:
    return _AGENTSCOPE_VERSION


# ─────────────────────────────────────────────────────────────────────
# Tool wrapper — normalize any callable into AgentScope's tool schema
# ─────────────────────────────────────────────────────────────────────
class Tool:
    """Lightweight AgentScope-compatible tool wrapper.

    Real AgentScope ships a richer Tool / Toolkit, but for the
    PPTagent pipeline we only need the surface we use: name,
    description, JSON schema for arguments, and an async call.
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        func: Callable[..., Awaitable[Any]] | Callable[..., Any],
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self._func = func
        self._is_coro = asyncio.iscoroutinefunction(func)

    async def __call__(self, **kwargs) -> Any:
        if self._is_coro:
            return await self._func(**kwargs)
        # Run sync funcs in a thread to keep the loop free.
        return await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._func(**kwargs),
        )

    def to_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ─────────────────────────────────────────────────────────────────────
# ReActAgent — LLM-driven tool selection loop
# ─────────────────────────────────────────────────────────────────────
class ReActAgent(_AgentScopeAgent):
    """ReAct loop over an AgentScope-style tool list.

    Concrete LLM wiring is left to the orchestrator (the orchestrator
    knows which model + prompt template to use); this class owns the
    loop: Thought → Action → Observation → repeat until done.

    Parameters
    ----------
    name:
        Agent identifier (passed up to AgentScope base).
    tools:
        List of `Tool` instances the LLM may call.
    model:
        Async callable `(messages) -> str` (or to a `Tool` request).
        If `None`, the agent runs in *stub* mode: it returns the
        first tool's result directly, which is enough for tests and
        for the fallback code path. Production wiring replaces this
        with a real LLM client.
    max_steps:
        Hard cap on ReAct iterations (default 8).
    """

    def __init__(
        self,
        name: str = "pptagent_react",
        tools: list[Tool] | None = None,
        model: Callable[[list[dict[str, Any]]], Awaitable[Any]] | None = None,
        max_steps: int = 8,
        **kwargs: Any,
    ) -> None:
        if not AGENTSCOPE_AVAILABLE:
            super().__init__(name=name, **kwargs)  # raises actionable error
        else:
            super().__init__(name=name, **kwargs)
        self.tools: dict[str, Tool] = {t.name: t for t in (tools or [])}
        self.model = model
        self.max_steps = max_steps
        self._trace: list[dict[str, Any]] = []

    def register_tool(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    @property
    def trace(self) -> list[dict[str, Any]]:
        return list(self._trace)

    async def invoke(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Run the ReAct loop and return the final assistant message + trace."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        for step in range(self.max_steps):
            self._trace.append({"step": step, "messages_count": len(messages)})
            if self.model is None:
                # Stub mode: pick the first tool deterministically.
                if not self.tools:
                    return {"content": "", "trace": self.trace, "stub": True}
                tool_name = next(iter(self.tools))
                tool = self.tools[tool_name]
                # Heuristic: pass the raw prompt as the only string field.
                observation = await tool(prompt=prompt, **kwargs)
                return {
                    "content": json.dumps(observation, default=str)[:2000],
                    "trace": self.trace,
                    "stub": True,
                    "tool": tool_name,
                }
            # Real model path: model returns either a message or a
            # tool-call request; we let the model object decide.
            response = await self.model(messages)
            messages.append({"role": "assistant", "content": str(response)})
            if isinstance(response, dict) and response.get("type") == "tool_call":
                tool_name = response["name"]
                tool = self.tools.get(tool_name)
                if tool is None:
                    messages.append({"role": "tool", "content": f"unknown tool: {tool_name}"})
                    continue
                observation = await tool(**response.get("arguments", {}))
                messages.append({"role": "tool", "content": json.dumps(observation, default=str)})
                continue
            return {"content": str(response), "trace": self.trace}
        return {"content": "", "trace": self.trace, "stopped_reason": "max_steps"}


# ─────────────────────────────────────────────────────────────────────
# HarnessAgent — fixed-pipeline orchestrator
# ─────────────────────────────────────────────────────────────────────
class HarnessAgent(_AgentScopeAgent):
    """Fixed-pipeline harness (Constitution §I, plan.md §3.2).

    The harness runs a strict stage sequence — it does NOT let the
    LLM choose tools. Each stage has a callable that receives the
    accumulated `state` and returns a state delta that gets merged in.
    The pipeline is the four stages of the PPTagent MVP:

        outline → points → svg → pptx

    Stages are registered up-front; the harness records per-stage
    timing + status into `state["_harness_trace"]`, which the
    orchestrator persists to the `trace_stages` table.
    """

    def __init__(
        self,
        name: str = "pptagent_harness",
        stages: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        if not AGENTSCOPE_AVAILABLE:
            super().__init__(name=name, **kwargs)
        else:
            super().__init__(name=name, **kwargs)
        # Each stage: {"name": str, "callable": async fn(state)->state}
        self.stages: list[dict[str, Any]] = stages or []
        self._trace: list[dict[str, Any]] = []

    def add_stage(
        self, name: str, fn: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    ) -> None:
        self.stages.append({"name": name, "callable": fn})

    @property
    def trace(self) -> list[dict[str, Any]]:
        return list(self._trace)

    async def invoke(self, state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Run all stages in order; stop on first failure."""
        state = dict(state)  # don't mutate caller's dict
        state.setdefault("_harness_trace", [])
        for stage in self.stages:
            name = stage["name"]
            fn = stage["callable"]
            entry: dict[str, Any] = {"name": name, "status": "running"}
            state["_harness_trace"].append(entry)
            try:
                if not asyncio.iscoroutinefunction(fn):
                    delta = await asyncio.get_running_loop().run_in_executor(
                        None,
                        lambda: fn(state),
                    )
                else:
                    delta = await fn(state)
                if delta:
                    state.update(delta)
                entry["status"] = "success"
            except Exception as e:
                entry["status"] = "failed"
                entry["error"] = repr(e)
                logger.exception("harness_stage_failed", stage=name, error=str(e))
                state["_last_error"] = {"stage": name, "error": repr(e)}
                break
        return state


__all__ = [
    "AGENTSCOPE_AVAILABLE",
    "Agent",
    "ContextConfig",
    "HarnessAgent",
    "ModelConfig",
    "ReActAgent",
    "ReActConfig",
    "Tool",
    "get_agentscope_version",
]


# Validate at import time so a missing editable install fails fast
# with a clear message instead of at first request.
if not AGENTSCOPE_AVAILABLE:
    logger.warning(
        "agentscope_not_importable",
        hint="Run `bash backend/scripts/install_local_deps.sh` (or .bat) "
        "to install the sibling `f:/workspace/PPT_Agent/AgentScope` "
        "repo in editable mode.",
    )
else:
    logger.info("agentscope_loaded", version=_AGENTSCOPE_VERSION)
