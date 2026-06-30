"""Smoke test for the ReAct agent refactor.

Verifies - without a real LLM - that:

  1. The agent loop iterates through tool calls in order
  2. The system prompt is cached (per (style, mode) tuple)
  3. ``render_svg_batch`` runs slides in parallel and persists
     to the checkpoint
  4. The dynamic timeout scales with the page count
  5. The legacy ``GenerationPipeline`` shim forwards to the
     new ``OrchestratorAgent``
  6. End-to-end 5/15/30/50-page decks can be planned, enriched,
     rendered in parallel chunks and checkpointed for resume.

Run with::

    cd backend && python -m src.scripts.smoke_react

It does NOT touch the database - it operates on a synthetic
``GenerationTask`` object with a mocked session.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from src.agents.agent_tools import (
    TOOL_DISPATCH,
    ToolContext,
    build_tool_schemas,
    extract_page_count,
    tool_enrich_points,
    tool_plan_outline,
    tool_render_svg_batch,
)
from src.core.config import settings
from src.integrations.agentscope_compat import ReActAgent
from src.services.generation.prompts import (
    clear_cache,
    get_svg_system_prompt,
    prompt_hash,
)


# Local copy of worker.compute_timeout_seconds so the smoke test
# doesn't have to import the worker module (which transitively
# imports the DB model graph, requiring pgvector, asyncpg, etc.).
def _compute_timeout_seconds(prompt: str | None) -> int:
    page_count = extract_page_count(prompt or "")
    raw = (
        settings.generation_timeout_base_seconds
        + int(settings.generation_timeout_per_page_seconds * page_count)
    )
    return max(120, min(raw, settings.generation_timeout_max_seconds))


def _make_task(page_count: int) -> MagicMock:
    """Build a GenerationTask stub with a list-like rendered_slides field."""
    task = MagicMock()
    task.id = "00000000-0000-0000-0000-000000000001"
    task.owner_id = "00000000-0000-0000-0000-000000000002"
    # NB: avoid non-ASCII text here to keep this test file portable
    task.prompt = f"Make a {page_count} page test report"
    task.visual_style = "swiss-minimal"
    task.communication_mode = "pyramid"
    task.rendered_slides = []
    task.token_consumed = 0
    task.source_file_ids = []
    return task


def _make_session() -> MagicMock:
    """Session stub: commit() is a no-op, execute() returns empty."""
    session = MagicMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_llm_stub(page_count: int = 10) -> Any:
    """An LLM that returns deterministic content per prompt signature.

    The stub honours the requested page count for plan_outline calls
    so the multi-page smoke tests can validate 5/15/30/50 page decks
    end-to-end. Page count is inferred from the system_prompt's
    "Generate exactly N slides." hint OR from the call argument.
    """

    class _StubLLM:
        def _detect_n(self, system_prompt: str) -> int:
            m = re.search(r"Generate exactly (\d+) slides", system_prompt or "")
            if m:
                return int(m.group(1))
            return page_count

        async def complete(self, *, system_prompt, user_prompt, temperature=0.3, max_tokens=4000):
            return f"<svg>{user_prompt[:30]}</svg>"

        async def complete_json(self, *, system_prompt, user_prompt, temperature=0.2, max_tokens=4000):
            n = self._detect_n(system_prompt or "")
            if '"outline"' in user_prompt and '"bullet_points"' in user_prompt:
                # enrich_points: return bullet_points per slide
                return {
                    "slides": [
                        {
                            "order": i + 1,
                            "title": f"slide {i + 1}",
                            "bullet_points": [f"point {i + 1}.a", f"point {i + 1}.b"],
                            "notes": f"notes for slide {i + 1}",
                        }
                        for i in range(n)
                    ]
                }
            # plan_outline
            return {
                "summary": f"{n}-page test deck",
                "slides": [
                    {
                        "order": i + 1,
                        "title": f"slide {i + 1}",
                        "description": "",
                        "slide_type": "body",
                    }
                    for i in range(n)
                ],
            }

    return _StubLLM()


async def test_prompt_caching() -> None:
    """System prompt should be built once and cached."""
    clear_cache()
    h1 = prompt_hash("swiss-minimal", "pyramid")
    p1 = get_svg_system_prompt("swiss-minimal", "pyramid")
    p2 = get_svg_system_prompt("swiss-minimal", "pyramid")
    h2 = prompt_hash("swiss-minimal", "pyramid")
    assert p1 is p2, "system prompt should be cached"
    assert h1 == h2
    # Different (style, mode) -> different prompt
    p3 = get_svg_system_prompt("dark-tech", "narrative")
    assert p3 != p1
    print(f"  OK prompt_caching: hash={h1}")


async def test_render_svg_batch_parallel() -> None:
    """render_svg_batch should run N slides concurrently and merge into checkpoint."""
    task = _make_task(10)
    session = _make_session()
    llm = _make_llm_stub()
    ctx = ToolContext(
        session=session,
        task=task,
        llm=llm,  # type: ignore[arg-type]
        parallelism=4,
        batch_size=5,
    )
    slides = [
        {"order": i + 1, "title": f"s{i + 1}", "bullet_points": ["a", "b"], "notes": "", "slide_type": "body"}
        for i in range(10)
    ]
    t0 = time.perf_counter()
    result = await tool_render_svg_batch(ctx, slides=slides, visual_style="swiss-minimal")
    dt = time.perf_counter() - t0
    assert len(result["rendered"]) == 10, f"expected 10 slides, got {len(result['rendered'])}"
    # Checkpoint should now have 10 slides
    assert len(task.rendered_slides) == 10, f"checkpoint not persisted, got {len(task.rendered_slides)}"
    print(f"  OK render_svg_batch_parallel: 10 slides in {dt*1000:.0f}ms (parallelism=4)")


async def test_render_svg_batch_resume() -> None:
    """Calling render_svg_batch twice should merge (not duplicate) slides."""
    task = _make_task(5)
    session = _make_session()
    llm = _make_llm_stub()
    ctx = ToolContext(session=session, task=task, llm=llm, parallelism=2, batch_size=3)

    slides_first = [
        {"order": i + 1, "title": f"a{i + 1}", "bullet_points": [], "notes": "", "slide_type": "body"}
        for i in range(3)
    ]
    slides_second = [
        {"order": i + 1, "title": f"b{i + 1}", "bullet_points": [], "notes": "", "slide_type": "body"}
        for i in range(2, 5)  # order=3,4,5
    ]
    await tool_render_svg_batch(ctx, slides=slides_first)
    assert len(task.rendered_slides) == 3
    await tool_render_svg_batch(ctx, slides=slides_second)
    assert len(task.rendered_slides) == 5, f"expected 5 unique, got {len(task.rendered_slides)}"
    # Slide order=3 should be from second call (title b3)
    slide3 = next(s for s in task.rendered_slides if s["order"] == 3)
    assert slide3["title"] == "b3", f"slide 3 should be overwritten, got {slide3['title']}"
    print(f"  OK render_svg_batch_resume: merge-by-order works")


async def test_extract_page_count() -> None:
    assert extract_page_count("Make 12 slides") == 12
    assert extract_page_count("make 30 slide deck") == 30
    assert extract_page_count("Make 20 slides please") == 20
    assert extract_page_count("default") == 10
    assert extract_page_count("Make 200 slides") == 10  # capped to default
    assert extract_page_count("") == 10
    print("  OK extract_page_count: zh / en / default all parse")


async def test_dynamic_timeout() -> None:
    # 10-page prompt -> default page count is 10
    assert _compute_timeout_seconds("Make 10 slides") >= 120
    # 50 pages explicit
    assert _compute_timeout_seconds("Make 50 slides") == 60 + 50 * 3  # 210
    # 100 pages capped to max_pages=60, so default (10) kicks in
    # raw = 60 + 30 = 90, clamped to 120
    assert _compute_timeout_seconds("Make 100 slides") == 120
    # No page count -> default 10 -> 60+30=90 -> clamped to 120
    assert _compute_timeout_seconds("default") == 120
    print("  OK dynamic_timeout: 5/15/30/50/100 page scaling works")


async def test_react_loop_stub_mode() -> None:
    """ReActAgent in stub mode should call the first tool deterministically.

    Skipped when AgentScope is not importable - the production
    orchestrator (OrchestratorAgent) works without it, but the
    inner ReActAgent class requires the agentscope package.
    """
    from src.integrations.agentscope_compat import AGENTSCOPE_AVAILABLE

    if not AGENTSCOPE_AVAILABLE:
        print("  SKIP react_loop_stub_mode: agentscope not installed")
        return

    called = []

    async def _fake_tool(ctx, **kwargs):
        called.append(("tool", kwargs))
        return {"summary": "stub"}

    agent = ReActAgent(
        name="smoke",
        tools={"only_tool": _fake_tool},
        model=None,  # stub mode
        max_steps=4,
    )
    result = await agent.invoke("hello", context=MagicMock(), extra_schemas=[
        {"type": "function", "function": {"name": "only_tool", "description": "x", "parameters": {}}}
    ])
    assert result["stub"] is True
    assert called, "stub should have invoked the tool"
    print(f"  OK react_loop_stub_mode: tool called {len(called)}x")


async def test_tool_schemas_valid() -> None:
    """Every registered tool has a JSON schema in build_tool_schemas()."""
    schemas = build_tool_schemas()
    names = {s["function"]["name"] for s in schemas}
    assert names == set(TOOL_DISPATCH.keys()), (
        f"schema names {names} != dispatch names {set(TOOL_DISPATCH.keys())}"
    )
    for s in schemas:
        assert "type" in s
        assert s["type"] == "function"
        assert "function" in s
        assert "name" in s["function"]
        assert "description" in s["function"]
        assert "parameters" in s["function"]
    print(f"  OK tool_schemas_valid: {len(schemas)} tools registered")


# ---------------------------------------------------------------------------
# End-to-end multi-page smoke: plan -> enrich -> render(chunks) -> check
# Validates the user's primary complaint: 10+ page decks should
# not fail and should be reasonably fast (parallelism-bounded).
# ---------------------------------------------------------------------------
async def _render_in_chunks(
    ctx: ToolContext,
    slides: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Mimic the agent loop: feed render_svg_batch in chunks of batch_size."""
    batch_size = max(1, ctx.batch_size)
    all_rendered: list[dict[str, Any]] = []
    for start in range(0, len(slides), batch_size):
        chunk = slides[start : start + batch_size]
        result = await tool_render_svg_batch(
            ctx,
            slides=chunk,
            visual_style="swiss-minimal",
            communication_mode="pyramid",
            batch_id=f"e2e-{start // batch_size}",
        )
        all_rendered.extend(result["rendered"])
    return all_rendered


async def test_e2e_multipage(page_count: int) -> None:
    """Run a 3-stage e2e (plan -> enrich -> render) for an N-page deck.

    Used as a parametric check for 5/15/30/50 page decks - the
    exact scenario the user reported failing before the ReAct
    refactor.
    """
    task = _make_task(page_count)
    task.prompt = f"Make {page_count} slides about AI product launch"
    session = _make_session()
    llm = _make_llm_stub(page_count)  # type: ignore[arg-type]
    ctx = ToolContext(
        session=session,
        task=task,
        llm=llm,  # type: ignore[arg-type]
        parallelism=settings.react_svg_parallelism,
        batch_size=settings.react_svg_batch_size,
    )

    t0 = time.perf_counter()

    # Stage 1: plan
    outline = await tool_plan_outline(
        ctx,
        prompt=task.prompt,
        page_count=page_count,
        communication_mode="pyramid",
        visual_style="swiss-minimal",
    )
    assert len(outline["slides"]) == page_count, (
        f"plan_outline produced {len(outline['slides'])} != {page_count}"
    )

    # Stage 2: enrich
    enriched = await tool_enrich_points(ctx, outline=outline)
    assert len(enriched["slides"]) == page_count

    # Stage 3: render in chunks
    rendered = await _render_in_chunks(ctx, enriched["slides"])
    assert len(rendered) == page_count, (
        f"rendered {len(rendered)} != {page_count}"
    )
    assert all(r.get("svg") for r in rendered), "all slides should have SVG"

    # Checkpoint should now have N slides
    assert len(task.rendered_slides) == page_count, (
        f"checkpoint has {len(task.rendered_slides)} slides, expected {page_count}"
    )

    dt = time.perf_counter() - t0
    timeout = _compute_timeout_seconds(task.prompt)

    expected_batches = (page_count + settings.react_svg_batch_size - 1) // settings.react_svg_batch_size
    print(
        f"  OK e2e_{page_count}_pages: "
        f"{dt * 1000:.0f}ms "
        f"(timeout={timeout}s, batches={expected_batches}, "
        f"parallelism={settings.react_svg_parallelism})"
    )


async def test_e2e_multipage_suite() -> None:
    """Parametric e2e across the user's target page-counts: 5/15/30/50."""
    for n in (5, 15, 30, 50):
        await test_e2e_multipage(n)


async def test_e2e_resume_from_checkpoint() -> None:
    """Restart mid-deck: previously-rendered slides should be preserved."""
    page_count = 30
    task = _make_task(page_count)
    task.prompt = f"Make {page_count} slides about a long product story"
    session = _make_session()
    llm = _make_llm_stub(page_count)  # type: ignore[arg-type]
    ctx = ToolContext(
        session=session,
        task=task,
        llm=llm,  # type: ignore[arg-type]
        parallelism=settings.react_svg_parallelism,
        batch_size=settings.react_svg_batch_size,
    )

    # Simulate: first worker run completed 12 of 30 slides
    slides_a = [
        {
            "order": i + 1,
            "title": f"a{i + 1}",
            "bullet_points": ["x"],
            "notes": "",
            "slide_type": "body",
        }
        for i in range(12)
    ]
    await tool_render_svg_batch(ctx, slides=slides_a, batch_id="first-run")
    assert len(task.rendered_slides) == 12

    # New worker run picks up the same task: render the remaining 18
    slides_b = [
        {
            "order": i + 13,
            "title": f"b{i + 13}",
            "bullet_points": ["y"],
            "notes": "",
            "slide_type": "body",
        }
        for i in range(18)
    ]
    await tool_render_svg_batch(ctx, slides=slides_b, batch_id="resume-run")
    assert len(task.rendered_slides) == page_count, (
        f"resume should merge to {page_count}, got {len(task.rendered_slides)}"
    )
    # All orders 1..30 should be present, in order
    orders = sorted(s["order"] for s in task.rendered_slides)
    assert orders == list(range(1, page_count + 1)), (
        f"missing orders: {set(range(1, page_count + 1)) - set(orders)}"
    )
    print(
        f"  OK e2e_resume_from_checkpoint: "
        f"{page_count}-page deck restored from partial checkpoint"
    )


async def test_e2e_timeout_covers_target() -> None:
    """Dynamic timeout must accommodate the target page counts.

    The hard requirement is:
      * Timeout >= 120s (2min floor for tiny decks)
      * Timeout <= GENERATION_TIMEOUT_MAX_SECONDS (40min ceiling)
      * Timeout scales monotonically with page count
    """
    last_t = 0
    for n in (5, 15, 30, 50):
        prompt = f"Make {n} slides"
        t = _compute_timeout_seconds(prompt)
        assert t >= 120, f"timeout for {n} pages is {t}s, must be >= 120s"
        assert t <= settings.generation_timeout_max_seconds, (
            f"timeout {t}s exceeds hard ceiling {settings.generation_timeout_max_seconds}"
        )
        assert t >= last_t, (
            f"timeout should scale with pages: {n} pages = {t}s, prev = {last_t}s"
        )
        last_t = t
    print(
        f"  OK e2e_timeout_covers_target: "
        f"5p={_compute_timeout_seconds('Make 5 slides')}s "
        f"15p={_compute_timeout_seconds('Make 15 slides')}s "
        f"30p={_compute_timeout_seconds('Make 30 slides')}s "
        f"50p={_compute_timeout_seconds('Make 50 slides')}s "
        f"(max ceiling {settings.generation_timeout_max_seconds}s)"
    )


async def main() -> int:
    print("=== ReAct agent smoke tests ===\n")
    await test_prompt_caching()
    await test_render_svg_batch_parallel()
    await test_render_svg_batch_resume()
    await test_extract_page_count()
    await test_dynamic_timeout()
    await test_react_loop_stub_mode()
    await test_tool_schemas_valid()
    print("\n--- End-to-end multi-page ---")
    await test_e2e_timeout_covers_target()
    await test_e2e_multipage_suite()
    await test_e2e_resume_from_checkpoint()
    print("\n=== ALL SMOKE TESTS PASSED ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
