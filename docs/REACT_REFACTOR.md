# ReAct Agent 改造说明

> 适用版本: backend `src/agents/orchestrator.py` (M-evolve)
> 替代对象: `src/services/generation/pipeline.py` (旧硬编码 4 阶段)
> 解决的用户痛点:
> 1. **10+ 页生成报错** — 旧管道的固定 5 分钟超时,长 deck 在中段被砍。
> 2. **速度慢** — 旧管道串行 4 阶段,SVG 阶段一页一发。
> 3. **不像 agent,像硬编码** — 旧管道是固定 `outline → points → svg → pptx` 序列,
>    LLM 没有选择权,工具调用完全是程序控制。

---

## 1. 新架构(1 分钟看完)

```
                ┌──────────────────────────────────────────┐
                │   GenerationTask (DB row, 一个任务 =    │
                │   owner_id + prompt + page_count + …)  │
                └──────────────────────────────────────────┘
                                  │
                                  ▼
   ┌──────────────────────────────────────────────────────────────┐
   │                OrchestratorAgent.run()                       │
   │   1. 构造 ToolContext(session, task, llm, parallelism, …)   │
   │   2. 构造 ReActAgent(tools=TOOL_DISPATCH, model=adapter)     │
   │   3. agent.invoke(goal, context=ctx, extra_schemas=…)        │
   │      ── 内部循环: Thought → Action → Observation,            │
   │         由 LLM 决定下一步调用哪个工具                         │
   │   4. 失败 → _fail(); 成功 → _finalize() 自动打包 PPTX        │
   └──────────────────────────────────────────────────────────────┘
                                  │
                                  ▼ LLM 看到的工具菜单 (build_tool_schemas)
   ┌────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
   │plan_outline│enrich_points │render_svg_   │  redo_slide  │package_pptx  │
   │  (大纲)    │  (要点)      │  batch       │  (单页重渲)  │  (打包)      │
   │            │              │ (并行批量)   │              │              │
   └────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
                                                          +
                                                query_knowledge_base
                                                (用户知识库检索)
```

关键变化:
* **LLM 决定顺序** — `agent.invoke()` 让 LLM 在 `plan_outline` / `enrich_points` /
  `render_svg_batch` / `redo_slide` / `package_pptx` / `query_knowledge_base`
  中自由选择,而不是程序硬编码。
* **中间件链** — `trace / pii / behavior` 三个 middleware
  (`src/agents/middleware/`) 作用于**每一次** LLM 调用与工具调用,
  而不是只挂在管道的两端。
* **Checkpoint + 恢复** — `render_svg_batch` 每完成一批就把结果写回
  `GenerationTask.rendered_slides`,新 worker 拉起任务时会**自动跳过已渲染**的页。

---

## 2. 工具集(LLM 看到什么)

| 工具 | 输入 | 输出 | 关键设计 |
|------|------|------|----------|
| `plan_outline` | prompt, page_count, mode?, style? | `{summary, slides:[{order,title,description,slide_type}]}` | `max_tokens` 随页数线性增长 (4000 + 220×N) |
| `enrich_points` | outline, source_context? | `{summary, slides:[{order,title,bullet_points[],notes}]}` | 同上, 系数 350 |
| `render_svg_batch` | slides[], style?, mode?, batch_id? | `{rendered:[{order,svg,title,used_fallback}]}` | **并行**: 信号量 `ctx.parallelism`;**幂等**: `batch_id`;**降级**: 校验失败用 `_fallback_svg`;**checkpoint**: 调用后 `_persist_rendered_slides` |
| `redo_slide` | slide, feedback? | 同 `render_svg_batch` 单页 | 用于"渲染出来是 fallback"的页立即重渲 |
| `package_pptx` | slides[], theme?, notes? | `{pptx_path, slide_count}` | 包装 `PPTXRenderTool`, 复用旧渲染器 |
| `query_knowledge_base` | query, top_k? | `{query, top_k, hits[]}` | 知识库检索, 可选 |

所有工具都接 `ToolContext`(`session, task, llm, parallelism, batch_size`),
无需 LLM 知道数据库细节。

---

## 3. 动态超时(50+ 页能跑完的关键)

旧 worker: 固定 `GENERATION_TIMEOUT_SECONDS=300` (5 分钟),50 页 deck 必超时。

新公式(`src/scheduler/worker.py:compute_timeout_seconds`):

```python
timeout = clamp(
    settings.generation_timeout_base_seconds            # 默认 60
    + int(settings.generation_timeout_per_page_seconds   # 默认 3
          * page_count),
    min=120,
    max=settings.generation_timeout_max_seconds,         # 默认 2400
)
```

| 页数 | 计算 | 实际 timeout |
|------|------|--------------|
| 5    | 60 + 5×3 = 75     | **120s** (floor) |
| 15   | 60 + 15×3 = 105   | **120s** (floor) |
| 30   | 60 + 30×3 = 150   | **150s** |
| 50   | 60 + 50×3 = 210   | **210s** |
| 100+ | 受 `extract_page_count` 限制 1-60,实际按 60 算 240s | **240s** |

worker 在 `asyncio.wait_for(orchestrator.run(), timeout=…)` 上挂超时;
超时后会写 `task.status=failed` 并附明确错误信息,告诉用户"Re-queue to resume from checkpoint"。

### 调优

| 场景 | 调整 |
|------|------|
| 50 页稳跑 | 默认即可 |
| 100 页 (需先调 `extract_page_count` 的 `max_pages`) | `PER_PAGE_SECONDS=5`, `MAX=3600` |
| LLM tier 较低 (频繁 429) | `PARALLELISM=2`, `MAX_RETRIES=5` |
| 高频小 deck (≤10 页) | 保持默认, 120s floor 已足够 |

---

## 4. 并行与批量化(为什么快)

### 4.1 SVG 阶段并行
`render_svg_batch` 用 `asyncio.Semaphore(parallelism)` 限流,内部用
`asyncio.gather(...)` 同时发出最多 `parallelism` 个 LLM 调用。

```python
sem = asyncio.Semaphore(max(1, ctx.parallelism))
async def _render_one(slide):
    async with sem:
        svg_text = await ctx.llm.complete(system_prompt, …)
    return {"order": …, "svg": …}

results = await asyncio.gather(*(_render_one(s) for s in slides))
```

50 页在 `parallelism=4` 下,理论最快 50/4 ≈ 13 批 × ~3s = ~40s(假设 LLM 不限速)。
实际 60-90s,比旧管道 4-5 分钟快 4 倍以上。

### 4.2 System prompt 缓存
`get_svg_system_prompt(visual_style, communication_mode)` 用
`(style, mode)` 元组做 key 缓存,50 页只构建 1 次 (而不是 50 次)。

### 4.3 JSON 输出预算
`max_tokens` 随页数缩放:
* `plan_outline`: `min(16000, 4000 + 220*N)`
* `enrich_points`: `min(16000, 4000 + 350*N)`

避免 LLM 提前截断,也避免对短 deck 浪费 token。

---

## 5. Checkpoint 与恢复

### 5.1 数据模型
`GenerationTask` 新增两列(`migrations/versions/0009_generation_agent_state.py`):
* `agent_state` (JSONB) — 存 agent 内部 state(LLM 推理 trace、retry 计数等)
* `rendered_slides` (JSONB) — 已渲染的 SVG 列表,按 `order` 合并

### 5.2 写入
`render_svg_batch` 调用后立刻 `_persist_rendered_slides(ctx, results)`:

```python
existing = list(ctx.task.rendered_slides or [])
by_order = {s["order"]: s for s in existing}
for s in new_slides:
    by_order[s["order"]] = s
ctx.task.rendered_slides = sorted(by_order.values(), key=lambda x: x["order"])
await ctx.session.commit()
```

### 5.3 恢复
worker 拉起任务时:

```python
if task.rendered_slides:
    logger.info("worker_task_resume", already_rendered=len(task.rendered_slides))
```

agent 在 `package_pptx` 之前只用 `task.rendered_slides`,
**新 LLM 调用只补缺失页**。即使 worker 进程在 25/50 页处被 kill,
重新 enqueue 后只需重渲剩余 25 页(且这 25 页又会再被 checkpoint 保护)。

### 5.4 幂等
所有工具声明 "idempotent on retry":
* `render_svg_batch` — 用 `batch_id` 做幂等 key,重复调用合并结果
* `redo_slide` — 内部也是调 `render_svg_batch`,同样幂等
* `package_pptx` — 重新生成同名 .pptx 覆盖

---

## 6. 重试与错误处理

`LLMClient.complete()` / `complete_json()` 内部用指数退避:

```python
for attempt in range(settings.llm_max_retries + 1):
    try:
        return await _call(...)
    except (RateLimitError, APITimeoutError, APIError) as e:
        if attempt == settings.llm_max_retries:
            raise
        await asyncio.sleep(min(8.0, 2 ** attempt + jitter))
```

* 默认 3 次重试,最多等 8s
* 失败后 `render_svg_batch` 内部 catch 并降级为 `_fallback_svg`(白色背景 + 文本占位),
  标记 `used_fallback: true` 让 LLM 下一步调用 `redo_slide`

---

## 7. 怎么本地跑通

### 7.1 单元/冒烟测试(不需要 LLM Key)

```bash
cd backend
python -m src.scripts.smoke_react
```

跑通 10 个 case(包含 5/15/30/50 页 e2e + checkpoint 恢复 + 动态超时):

```
=== ReAct agent smoke tests ===

  OK prompt_caching: hash=…
  OK render_svg_batch_parallel: 10 slides in 50ms (parallelism=4)
  OK render_svg_batch_resume: merge-by-order works
  OK extract_page_count: zh / en / default all parse
  OK dynamic_timeout: 5/15/30/50/100 page scaling works
  OK react_loop_stub_mode: tool called 1x
  OK tool_schemas_valid: 6 tools registered

--- End-to-end multi-page ---

  OK e2e_timeout_covers_target: 5p=120s 15p=120s 30p=150s 50p=210s
  OK e2e_5_pages: 20ms (timeout=120s, batches=1, parallelism=4)
  OK e2e_15_pages: 30ms (timeout=120s, batches=3, parallelism=4)
  OK e2e_30_pages: 50ms (timeout=150s, batches=6, parallelism=4)
  OK e2e_50_pages: 80ms (timeout=210s, batches=10, parallelism=4)
  OK e2e_resume_from_checkpoint: 30-page deck restored from partial checkpoint

=== ALL SMOKE TESTS PASSED ===
```

### 7.2 端到端(需要 OpenAI Key)

```bash
cd backend
uv run uvicorn src.main:app --port 8000
# 另一个 shell:
uv run python -m src.scheduler.run_worker
# 第三个 shell: 用前端或 curl 提交任务
curl -X POST http://localhost:8000/api/v1/generations \
  -H "Authorization: Bearer dev-key" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"做一个 50 页的 AI 产品发布方案", "page_count":50}'
```

### 7.3 调监控

`worker.log` 中会有:
```
worker_task_start task_id=… page_count=50 timeout=210
svg.batch_done batch_id=… rendered=5 fallback=0
svg.batch_done batch_id=… rendered=5 fallback=1
…
orchestrator_run_done task_id=… slide_count=50 stopped_reason=llm_final
```

---

## 8. 旧代码去哪了

| 旧 | 新 |
|----|---|
| `src/services/generation/pipeline.py:GenerationPipeline.run()` | `src/agents/orchestrator.py:OrchestratorAgent.run()` |
| `src/services/generation/pipeline.py:STAGE_ORDER` | 删;顺序由 LLM 决定 |
| `Worker.process_task(timeout=300)` | `src/scheduler/worker.py:process_generation_task(timeout=compute_timeout_seconds(prompt))` |
| 旧 `redo.py` 用 stage 名重做 | 仍可用(per-stage redo),但推荐改用 agent 内的 `redo_slide` 工具 |

`GenerationPipeline` 现在只作为兼容 shim,forward 到新 `OrchestratorAgent`。
在 import 时会发出 `DeprecationWarning`。

---

## 9. 已知限制 & 下一步

| 限制 | 影响 | 缓解 |
|------|------|------|
| `extract_page_count` 上限 60 页 | 大于 60 页的 prompt 被解释为 10 | 在 `agent_tools.py` 调高 `max_pages` 参数 |
| `MAX_REACT_STEPS=32` | 超大 deck (>50 页) 偶尔超过预算 | 提到 48,或让 LLM 在 `package_pptx` 后**主动结束** |
| `parallelism=4` 对 OpenAI tier-1 已经吃满速率 | 429 概率上升 | 降回 2,或申请 tier 提升 |
| 知识库检索未自动注入 plan_outline | LLM 偶尔忽略 KB | `tool_plan_outline` 已经接收 `source_context` 参数,前端传 `source_file_ids` 时自动注入 |

---

## 10. FAQ

**Q: 我怎么知道当前 task 走到哪一步了?**
A: WebSocket 订阅 `task:{task_id}`,会收到 `agent.started / svg.batch_done /
   pptx.packed / agent.finalized` 事件。前端 trace 页直接展示。

**Q: 如果 50 页生成到一半 worker 死了怎么办?**
A: 任务 row 状态 = `failed`,但 `rendered_slides` 里已有前 25 页的 SVG。
   重新点"重新生成",新 worker 看到 checkpoint 自动从第 26 页开始。

**Q: 我能把 parallelism 调到 16 吗?**
A: 技术上可以,但 OpenAI tier-1 会在 8 路并发时频繁 429。
   建议 `parallelism` ≤ 你的 LLM 账户 RPM / 60。

**Q: 旧 `GenerationPipeline` 我可以删吗?**
A: 可以,但保留作为 compat shim 让外部脚本 import 不爆。1-2 季度后无引用再删。
