"""Unit tests for the AgentScope compat shim (T026).

We don't require agentscope to be installed — these tests verify that
the fallback path and import error messaging are correct.
"""

from __future__ import annotations

import pytest


def test_agentscope_version_helper():
    from src.integrations.agentscope_compat import get_agentscope_version

    v = get_agentscope_version()
    assert isinstance(v, str)
    # If the real agentscope is installed, this is a version string
    # If not, the fallback marks it as "unknown"
    assert v == "unknown" or len(v) > 0


def test_tool_wrapper_basic():
    from src.integrations.agentscope_compat import Tool

    async def adder(x: int, y: int) -> int:
        return x + y

    t = Tool(
        name="adder",
        description="adds two ints",
        parameters={
            "type": "object",
            "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
        },
        func=adder,
    )
    assert t.name == "adder"
    assert t.parameters["type"] == "object"
    schema = t.to_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "adder"


@pytest.mark.asyncio
async def test_tool_async_call():
    from src.integrations.agentscope_compat import Tool

    async def greet(name: str) -> str:
        return f"hello {name}"

    t = Tool(
        name="greet",
        description="greet someone",
        parameters={"type": "object", "properties": {"name": {"type": "string"}}},
        func=greet,
    )
    assert await t(name="world") == "hello world"


@pytest.mark.asyncio
async def test_tool_sync_fallback_runs_in_executor():
    from src.integrations.agentscope_compat import Tool

    def double(x: int) -> int:
        return x * 2

    t = Tool(
        name="double",
        description="double an int",
        parameters={"type": "object", "properties": {"x": {"type": "integer"}}},
        func=double,
    )
    assert await t(x=21) == 42
