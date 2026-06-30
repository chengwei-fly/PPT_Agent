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
    """Production ReAct loop over an AgentScope-style tool list.

    Parameters
    ----------
    name:
        Agent identifier (passed up to AgentScope base).
    tools:
        Either a list of `Tool` instances OR a mapping of
        ``{name: async_callable}`` for tools that accept a
        context object (the production PPTagent path).
    model:
        Async callable that takes ``(system, messages, tool_schemas)``
        and returns a dict with one of:
          * ``{"type": "tool_call", "name": str, "arguments": dict}``
          * ``{"type": "final", "content": str}``
        If ``None``, the agent runs in *stub* mode (tests only).
    system_prompt:
        Optional system prompt passed on every LLM call.
    max_steps:
        Hard cap on ReAct iterations (default 16).
    middleware:
        Optional list of async callables ``(event_name, payload)`` for
        trace / PII / behavior middleware (Constitution §V).
    """

    def __init__(
        self,
        name: str = "pptagent_react",
        tools: list[Tool] | dict[str, Any] | None = None,
        model: Callable[..., Awaitable[Any]] | None = None,
        system_prompt: str = "",
        max_steps: int = 16,
        middleware: list[Callable[[str, dict[str, Any]], Awaitable[None]]] | None = None,
        **kwargs: Any,
    ) -> None:
        if not AGENTSCOPE_AVAILABLE:
            # Stub mode: AgentScope is not installed, but the
            # ``agentscope.agent.Agent`` parent may still demand
            # system_prompt / model positionally. Pass them through
            # to keep the stub importable for tests.
            super().__init__(  # type: ignore[misc]
                name=name,
                system_prompt=system_prompt,
                model=model,
                **kwargs,
            )
        else:
            super().__init__(name=name, system_prompt=system_prompt, model=model, **kwargs)
        # Normalize tool registry. Two shapes are supported:
        #   1) list[Tool]  — used by tests / external integrations
        #   2) dict[name, callable] — production path: tools receive a
        #      ToolContext (first positional) and **kwargs from the LLM.
        if isinstance(tools, dict):
            self._tool_funcs: dict[str, Callable[..., Awaitable[Any]]] = tools
            self.tools: dict[str, Tool] = {}  # type: ignore[assignment]
        else:
            self._tool_funcs = {}
            self.tools = {t.name: t for t in (tools or [])}  # type: ignore[assignment]
        self.model = model
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.middleware = middleware or []
        self._trace: list[dict[str, Any]] = []

    def register_tool(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def register_function(self, name: str, func: Callable[..., Awaitable[Any]]) -> None:
        """Register a tool function that takes ToolContext + kwargs."""
        self._tool_funcs[name] = func

    @property
    def trace(self) -> list[dict[str, Any]]:
        return list(self._trace)

    def available_tool_names(self) -> list[str]:
        """All tools visible to the LLM (function-style + Tool-style)."""
        names = set(self._tool_funcs.keys()) | set(self.tools.keys())
        return sorted(names)

    def tool_schemas(self) -> list[dict[str, Any]]:
        """Return JSON schemas for ALL registered tools.

        For function-style tools, the schema is supplied externally
        via the orchestrator (since the callable signature is opaque
        to us). For Tool-style, we use Tool.to_schema().
        """
        schemas: list[dict[str, Any]] = []
        for t in self.tools.values():
            schemas.append(t.to_schema())
        # Function-style schemas are added via ``extra_schemas`` in
        # invoke() — the orchestrator knows the JSON shapes.
        return schemas

    async def _emit(self, event_name: str, payload: dict[str, Any]) -> None:
        """Run an event through the middleware chain."""
        for mw in self.middleware:
            try:
                await mw(event_name, payload)
            except Exception as e:  # pragma: no cover
                logger.warning(
                    "middleware_error",
                    event=event_name,
                    error=str(e),
                )

    async def _dispatch(
        self,
        name: str,
        arguments: dict[str, Any],
        context: Any = None,
    ) -> Any:
        """Call a registered tool. Returns the tool's return value."""
        if name in self._tool_funcs:
            func = self._tool_funcs[name]
            if context is not None:
                return await func(context, **arguments)
            return await func(**arguments)
        if name in self.tools:
            return await self.tools[name](**arguments)
        raise KeyError(f"unknown tool: {name}")

    async def invoke(
        self,
        prompt: str,
        *,
        context: Any = None,
        extra_schemas: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run the ReAct loop and return the final assistant message + trace.

        ``context`` is the first positional arg passed to function-style
        tools (e.g. ``ToolContext``). ``extra_schemas`` supplies the JSON
        shapes for function-style tools so the LLM knows how to call them.
        """
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        schemas = self.tool_schemas() + list(extra_schemas or [])

        for step in range(self.max_steps):
            self._trace.append({"step": step, "messages_count": len(messages)})
            await self._emit(
                "react.step",
                {"step": step, "messages": len(messages), "tools": self.available_tool_names()},
            )

            if self.model is None:
                # Stub mode: pick the first available tool deterministically.
                if not self.available_tool_names():
                    return {"content": "", "trace": self.trace, "stub": True}
                tool_name = self.available_tool_names()[0]
                tool_args = kwargs or {"prompt": prompt}
                observation = await self._dispatch(tool_name, tool_args, context=context)
                return {
                    "content": json.dumps(observation, default=str)[:2000],
                    "trace": self.trace,
                    "stub": True,
                    "tool": tool_name,
                }

            # Real model path
            response = await self.model(
                system=self.system_prompt,
                messages=messages,
                tools=schemas,
            )

            if isinstance(response, dict) and response.get("type") == "tool_call":
                tool_name = response.get("name") or ""
                tool_args = response.get("arguments") or {}
                self._trace.append(
                    {"step": step, "tool_call": tool_name, "args_keys": list(tool_args.keys())}
                )
                await self._emit(
                    "tool_invocation",
                    {
                        "step": step,
                        "name": tool_name,
                        "arguments": tool_args,
                    },
                )
                try:
                    observation = await self._dispatch(tool_name, tool_args, context=context)
                except Exception as e:
                    logger.exception("tool_call_failed", tool=tool_name, error=str(e))
                    observation = {"error": repr(e), "tool": tool_name}
                    await self._emit(
                        "tool_error",
                        {"step": step, "name": tool_name, "error": str(e)},
                    )

                messages.append({"role": "assistant", "content": json.dumps(response, default=str)})
                messages.append(
                    {
                        "role": "tool",
                        "name": tool_name,
                        "content": json.dumps(observation, default=str)[:8000],
                    }
                )
                await self._emit(
                    "tool_result",
                    {
                        "step": step,
                        "name": tool_name,
                        "observation_keys": (
                            list(observation.keys())
                            if isinstance(observation, dict)
                            else type(observation).__name__
                        ),
                    },
                )
                continue

            # Final answer
            final_content = response.get("content", str(response)) if isinstance(response, dict) else str(response)
            messages.append({"role": "assistant", "content": str(final_content)})
            await self._emit("react.final", {"step": step, "content_preview": str(final_content)[:200]})
            return {"content": str(final_content), "trace": self.trace, "messages": messages}

        # Hit max_steps — surface a synthetic final answer so callers
        # can still pick up state from the messages log.
        await self._emit("react.max_steps", {"max_steps": self.max_steps})
        return {
            "content": "",
            "trace": self.trace,
            "messages": messages,
            "stopped_reason": "max_steps",
        }


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
