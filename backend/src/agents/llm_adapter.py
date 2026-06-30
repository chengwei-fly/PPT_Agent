"""LLM adapter that bridges ``LLMClient`` to the ReActAgent's model hook.

The ReActAgent invokes the model as::

    response = await model(system=..., messages=..., tools=...)

and expects one of:

  * ``{"type": "tool_call", "name": str, "arguments": dict}``
  * ``{"type": "final", "content": str}``

This adapter makes a single LLMClient chat-completion call per
``model(...)`` invocation and parses the response:

  * If the model returns a tool call (in the OpenAI ``tool_calls``
    array, or as a JSON-encoded ``final`` answer), we surface it
    as a ``tool_call`` event.
  * If the model returns plain text, we surface it as a ``final``
    event (the agent loop ends).
  * If parsing fails, we fall back to a ``final`` event carrying
    the raw text so the agent can still terminate gracefully.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.core.observability import get_logger
from src.services.generation.llm_client import LLMClient

logger = get_logger("llm_adapter")


# Reasonable output cap for one model invocation inside the
# ReAct loop. The planner is small; the heavy payloads
# (outline JSON, points JSON) come from the tools themselves.
_LOOP_MAX_TOKENS = 4000


class ReactLLMAdapter:
    """Wrap an LLMClient so it can drive the ReActAgent loop.

    Tool schemas are pre-rendered into a textual section and
    injected on the FIRST model call only. Subsequent calls
    include a short reminder ("Use the tools documented in the
    original system prompt if needed") so we don't pay the
    full system-prompt cost on every ReAct iteration. This
    halves the input-token bill for long 50-page decks where
    the loop runs 15-20 steps.
    """

    _TOOLS_REMINDER = (
        "\n\n## Tool reminder\n"
        "The available tools were described in the original "
        "system prompt; you may invoke them by returning a JSON "
        "object {\"type\": \"tool_call\", \"name\": \"<tool>\", "
        "\"arguments\": {…}}."
    )

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self._tools_sent = False

    async def __call__(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        # Inject the tool schemas into the system prompt so the
        # model knows what's available. We don't use the
        # OpenAI-native ``tools`` field because the model we ship
        # with (``gpt-4o-mini``) supports it, but downstream
        # OpenAI-compatible providers (DashScope, OpenRouter)
        # sometimes ignore it — so we fall back to a textual
        # description that works everywhere.
        full_system = system or ""
        if not self._tools_sent:
            tool_section = _render_tools_section(tools or [])
            if tool_section:
                full_system = (
                    f"{full_system}\n\n{tool_section}" if full_system else tool_section
                )
            self._tools_sent = True
        else:
            # Reminder only — saves ~1k tokens per ReAct step
            # on long decks (30+ pages → 10+ steps → ~10k saved).
            full_system = f"{full_system}{self._TOOLS_REMINDER}" if full_system else self._TOOLS_REMINDER.lstrip("\n")

        # The ReAct loop's message log uses a "tool" role for
        # observations; some OpenAI-compatible endpoints reject
        # unknown roles. Rewrite to "user" with a structured
        # prefix instead.
        normalized = [_normalize_message(m) for m in messages]

        try:
            text = await self.llm.complete(
                system_prompt=full_system,
                user_prompt=_messages_to_prompt(normalized),
                temperature=0.2,
                max_tokens=_LOOP_MAX_TOKENS,
            )
        except Exception as e:
            logger.exception("react_llm_call_failed", error=str(e))
            return {"type": "final", "content": f"LLM error: {e!r}"}

        # Try to parse a tool call from the response
        tool_call = _try_parse_tool_call(text, tools or [])
        if tool_call is not None:
            return {
                "type": "tool_call",
                "name": tool_call["name"],
                "arguments": tool_call["arguments"],
            }

        return {"type": "final", "content": text}


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def _normalize_message(m: dict[str, Any]) -> dict[str, Any]:
    """Make any ReAct-loop message OpenAI-compatible."""
    role = m.get("role", "user")
    content = m.get("content", "")
    if role == "tool":
        # Rewrite tool observations as user messages
        name = m.get("name", "tool")
        return {
            "role": "user",
            "content": f"Tool [{name}] returned:\n{content}",
        }
    if role == "assistant" and not isinstance(content, str):
        return {"role": "assistant", "content": str(content)}
    return {"role": role, "content": content if isinstance(content, str) else str(content)}


def _messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    """Flatten the message log to a single user-prompt string.

    The model is given the full message history in textual form
    so it can reason about past tool calls.
    """
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "assistant":
            parts.append(f"ASSISTANT:\n{content}")
        elif role == "user":
            parts.append(f"USER:\n{content}")
        elif role == "system":
            continue
        else:
            parts.append(f"{role.upper()}:\n{content}")
    return "\n\n---\n\n".join(parts) or "(empty)"


def _render_tools_section(tools: list[dict[str, Any]]) -> str:
    """Render a textual description of the available tools."""
    if not tools:
        return ""
    lines = ["## Available tools", ""]
    lines.append(
        "You MUST respond with EITHER:\n"
        "  (a) a single JSON object {\"type\": \"final\", \"content\": \"<your final answer>\"}\n"
        "  (b) a single JSON object {\"type\": \"tool_call\", \"name\": \"<tool>\", \"arguments\": {<args>}}\n"
        "Do not include any other text. Do not wrap the JSON in markdown fences.\n"
    )
    for schema in tools:
        fn = schema.get("function", {})
        name = fn.get("name", "?")
        desc = fn.get("description", "")
        params = fn.get("parameters", {}) or {}
        lines.append(f"### {name}")
        lines.append(desc)
        props = params.get("properties", {})
        required = params.get("required", [])
        if props:
            lines.append("Arguments:")
            for pname, pschema in props.items():
                req = " (required)" if pname in required else ""
                ptype = pschema.get("type", "any")
                pdesc = pschema.get("description", "")
                lines.append(f"  - `{pname}` ({ptype}){req}: {pdesc}")
        lines.append("")
    return "\n".join(lines)


def _try_parse_tool_call(
    text: str,
    tools: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Extract a ``{name, arguments}`` dict from the model output.

    Accepts:
      * raw JSON: ``{"type":"tool_call", "name":..., "arguments":{...}}``
      * JSON wrapped in ```json fences
      * JSON embedded anywhere in the text (regex fallback)
    """
    candidate = text.strip()
    if candidate.startswith("```"):
        # Strip code fences
        first_nl = candidate.find("\n")
        if first_nl != -1:
            candidate = candidate[first_nl + 1 :]
        if candidate.endswith("```"):
            candidate = candidate[:-3].strip()

    valid_names = {
        (t.get("function", {}) or {}).get("name", "") for t in tools
    } - {""}

    # 1) Try strict JSON
    parsed: Any = None
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        # 2) Find a JSON object in the text
        m = re.search(r"\{.*\}", candidate, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
        else:
            return None

    if not isinstance(parsed, dict):
        return None

    # 3) Direct tool_call shape
    if parsed.get("type") == "tool_call":
        name = parsed.get("name", "")
        args = parsed.get("arguments") or {}
        if name in valid_names:
            return {"name": name, "arguments": args}
        return None

    # 4) Older shape: just ``{"name": ..., "arguments": ...}``
    name = parsed.get("name", "")
    args = parsed.get("arguments") or {}
    if name in valid_names and isinstance(args, dict):
        return {"name": name, "arguments": args}

    return None


__all__ = ["ReactLLMAdapter"]
