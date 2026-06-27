# Implementation Plan: PPTagent MVP 业务闭环

**Branch**: `001-mvp-closed-loop` | **Date**: 2026-06-24 | **Spec**: [spec.md](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/spec.md)

**Input**: Feature specification from `/specs/001-mvp-closed-loop/spec.md` (含 5 US、29 FR、14 SC、6 Entities)

**Note**: 本计划由 `/speckit.plan` 生成。Phase 0 输出见 [research.md](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/research.md)；Phase 1 输出见 [data-model.md](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/data-model.md)、[quickstart.md](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/quickstart.md) 与 [contracts/](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/contracts/)。

---

## Summary

构建面向"产品 / 方案人员"的垂类智能 PPT 生成平台 MVP 闭环：以"上传个人 PPT/PDF/Word → 一句话生成风格对齐的 PPT"为最小业务闭环，覆盖 M1（生成链路）→ M2（个人知识库）→ M3（Agent 进化引擎）→ M4（去 AI 味 + 私有化 Beta）四阶段 12 周路线图。技术路线在 `ppt-master`（生成引擎）与 `AgentScope 2.0`（编排框架）两个成熟开源项目上做二开，所有 AI 行为可解释、可回滚、可观测，所有用户数据安全前置。

---

## Technical Context

| 维度 | 选型 | 来源 |
|------|------|------|
| **Language/Version - Frontend** | TypeScript 5.x + Node 20 LTS | Constitution §技术栈 |
| **Language/Version - Backend** | Python 3.11+ | Constitution §技术栈 |
| **Frontend Framework** | React 18 + Vite + Tailwind CSS + shadcn/ui | Constitution §技术栈 |
| **Backend Framework** | FastAPI + Uvicorn + Pydantic v2 | Constitution §技术栈 |
| **Agent Framework** | AgentScope 2.0（`ReActAgent` + `HarnessAgent`） | Constitution §I |
| **Generation Engine** | `ppt-master`（SVG→DrawingML→PPTX 管线） | Constitution §I |
| **Primary Database** | PostgreSQL 16 | Constitution §技术栈 |
| **Vector Store** | pgvector（短期） | Constitution §技术栈 |
| **Object Storage** | MinIO（开发）/ S3 兼容（生产） | Constitution §技术栈 |
| **Cache & Queue** | Redis 7 | Constitution §技术栈 |
| **Testing - Unit/Contract** | pytest + Pact | Constitution §VI |
| **Testing - E2E** | Playwright（Web） | Constitution §VI |
| **Observability** | OpenTelemetry + 结构化 JSON 日志 + jaeger | Constitution §V |
| **Target Platform** | Linux 容器化（Docker + Kubernetes 预留） | Constitution §技术栈 |
| **Project Type** | Web 应用程序（Frontend + Backend） | Constitution §技术栈 |
| **Performance Goals** | SC-001：5 分钟内 95% 交付率；SC-009：阶段重做节省 ≥ 60% | spec §Success Criteria |
| **Constraints** | FR-006：单文件 ≤ 50MB、批量 ≤ 20 份；FR-004：Token 预估前置 | spec §FR |
| **Scale/Scope** | SC-011：私有化 Beta ≥ 3 家 / SC-003：3 步完成生成 | spec §SC |
| **SLA** | FR-024：月度 ≥ 99%；FR-025：MTTR ≤ 4h | spec §FR |
| **Data Retention** | FR-026：样本/偏好长期；FR-027：任务 180d | spec §FR |
| **Concurrency** | FR-029：单用户 ≤ 2 并发；第 3 入队 + 5min 超时 | spec §FR |

> 0 项 NEEDS CLARIFICATION（spec 阶段的 5 项澄清已全部落地为可测试的 FR/SC）

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

PPTagent Constitution v1.0.0 合规性预检 — 每项 MUST 标记 ✅ / ⚠ / ❌：

| # | 原则 | 状态 | 落地点 |
|---|------|------|--------|
| **I** | 二开优先与资产复用 | ✅ | 核心生成 = `ppt-master` SVG→DrawingML→PPTX；Agent = `AgentScope 2.0` `ReActAgent` + `HarnessAgent`；不引入 LangChain/AutoGen |
| **II** | MVP 驱动与业务闭环 | ✅ | 12 周 / 4 里程碑分阶段（见 §Milestone Mapping），所有任务按 [CORE]/[KB]/[EVOL]/[INFRA] 标签归位 |
| **III** | AI 生成可解释与可控制 | ✅ | FR-015/016 4 阶段生成轨迹；FR-017 撤销 / 锁定原文；FR-008 PII 字段级处置 |
| **IV** | 数据安全与隐私前置 | ✅ | FR-008/009/018/019/020；PII 中间件 + 三类数据分离 + API Key 网关 |
| **V** | Agent 行为可观测与可追溯 | ✅ | FR-022 三标签 trace；FR-023 运维指标；`ppt_render` / `preference_update` 等结构化事件 |
| **VI** | 测试驱动与质量门禁 | ✅ | 6 阶段 CI（lint→单测→契约→端到端→安全→Token 预算）；5 种典型样本回归库 |
| **VII** | 语义化版本与依赖锁定 | ✅ | 依赖 `ppt-master` / `AgentScope 2.0` 通过 `pyproject.toml` 锁文件固定 commit/tag；`MAJOR.MINOR.PATCH` 策略 |

> 无违规。Complexity Tracking 表留空。

---

## Project Structure

### Documentation（本 feature）

```text
specs/001-mvp-closed-loop/
├── plan.md              # 本文件
├── research.md          # Phase 0：选型与替代方案
├── data-model.md        # Phase 1：6 实体数据模型
├── quickstart.md        # Phase 1：本地开发启动
├── contracts/           # Phase 1：OpenAPI 3.1 契约
│   ├── openapi.yaml
│   ├── events.yaml      # WebSocket 事件契约
│   └── error-codes.yaml # RFC 7807 错误码
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2：/speckit.tasks 输出
```

### Source Code（仓库根目录）

**Structure Decision**: **Option 2: Web application**（Frontend + Backend）。理由：spec 同时涉及"网页交互"（US1–US5）和"后端生成链路"（M1 编排），单仓分离前后端是 Constitution §技术栈已锁定的标准形态。

```text
backend/
├── src/
│   ├── api/                    # FastAPI 路由
│   │   ├── generations.py      # POST /generations, GET /generations/{id}
│   │   ├── samples.py          # CRUD /samples, POST /samples/batch
│   │   ├── preferences.py      # GET/DELETE /preferences
│   │   ├── traces.py           # GET /generations/{id}/trace
│   │   ├── data_lifecycle.py   # POST /data/export, /data/delete-all
│   │   ├── security.py         # GET /security/events
│   │   └── ops.py              # GET /healthz, /metrics
│   ├── core/
│   │   ├── config.py           # Pydantic Settings
│   │   ├── security.py         # API Key 网关（最小权限 + 速率限制）
│   │   ├── pii.py              # PII 检测中间件（手机/邮箱/身份证/客户名）
│   │   ├── observability.py    # OTel + 结构化 JSON
│   │   └── lifespan.py         # FastAPI 启动/关闭钩子
│   ├── models/                 # Pydantic v2 DTO（与 OpenAPI 自动同步）
│   │   ├── user.py
│   │   ├── sample.py
│   │   ├── preference.py
│   │   ├── generation_task.py
│   │   ├── trace_stage.py
│   │   └── security_event.py
│   ├── services/
│   │   ├── generation/         # 编排服务
│   │   ├── knowledge_base/     # 解析 + 入库 + 双模检索
│   │   ├── preference/         # 偏好提取 + 应用
│   │   ├── data_lifecycle/     # 导出 + 删除 + 归档
│   │   └── scoring/            # 风格契合度三层指标
│   ├── agents/                 # AgentScope 2.0 编排
│   │   ├── orchestrator.py     # HarnessAgent 包装
│   │   ├── react_agent.py      # ReActAgent 实例
│   │   └── middleware/
│   │       ├── pii_middleware.py
│   │       ├── trace_middleware.py
│   │       └── behavior_middleware.py
│   ├── tools/                  # Agent 可调用的 Tool
│   │   ├── svg2pptx.py         # 对接 ppt-master
│   │   ├── sample_parser.py    # PPTX/PDF/DOCX 解析
│   │   ├── knowledge_retriever.py  # 双模检索
│   │   └── pii_detector.py     # 独立 PII 工具
│   ├── db/                     # PostgreSQL + pgvector
│   │   ├── session.py
│   │   ├── models/             # SQLAlchemy ORM
│   │   └── migrations/         # Alembic
│   ├── storage/                # MinIO/S3 客户端
│   ├── scheduler/              # Redis 队列 + FIFO + 5min 超时
│   │   ├── queue.py
│   │   └── worker.py
│   └── main.py
├── tests/
│   ├── unit/
│   ├── contract/               # Pact 提供者/消费者
│   ├── integration/            # 含 5 种典型样本的回归
│   ├── e2e/                    # Playwright
│   └── fixtures/samples/       # 真实样本库（汇报/培训/方案/数据/营销）
├── pyproject.toml              # 锁文件：ppt-master commit / AgentScope 2.0 tag
└── Dockerfile

frontend/
├── src/
│   ├── components/
│   │   ├── ui/                 # shadcn/ui primitives
│   │   ├── generation/         # 一句话输入、进度、取消、下载
│   │   ├── knowledge/          # 上传、列表、删除
│   │   ├── preferences/        # 我的偏好页面
│   │   ├── trace/              # 生成轨迹可视化 + 阶段重做
│   │   ├── security/           # 安全事件列表
│   │   └── data_lifecycle/     # 导出/删除/归档
│   ├── pages/                  # 路由级页面
│   ├── services/               # OpenAPI 自动生成的 TS client
│   ├── stores/                 # Zustand
│   ├── hooks/                  # useGeneration / useSamples / useQueue
│   ├── router/                 # React Router 6
│   └── main.tsx
├── tests/
│   ├── unit/                   # vitest
│   └── e2e/                    # Playwright
├── package.json
└── Dockerfile
```

### Milestone Mapping（任务 ↔ 里程碑）

| 里程碑 | 周次 | 主线 | 核心交付 |
|--------|------|------|----------|
| **M1 生成链路** | W1–W3 | CORE | `OrchestratorAgent` + `SVG2PPTXTool` 端到端打通；US1 MVP；同时启动 US6 解析链路（SlideExtractor 抽页，PG 迁移 0007 表结构搭好但搜索服务不阻塞 M1） |
| **M2 知识库** | W4–W6 | KB | 解析 + 双模检索；US2 闭环；FR-008 PII 中间件；**US6 素材库双路检索（BM25 + 嵌入）MVP**，交付 `GET /materials` 单页可用 |
| **M3 Agent 进化** | W7–W9 | EVOL | `PreferenceExtractor` + `BehaviorMiddleware`；US3 + US4；**US6 草稿编辑 + 风格归一工具 + 单写者锁** |
| **M4 打磨 / Beta** | W10–W12 | INFRA + QA | 风格契合度评分落地 + SLA 监控 + 私有化 Beta 候选 ≥ 3 家；US5；**US6 导出溯源（XMP）+ 索引同步 + 端到端素材复用回归套件** |
| **M5 切片（US6 闭环）** | 与 M2/M3 同步 | US6 | 端到端 "搜索 → 插入 → 编辑 → 导出 PPTX"；SC-015 P95 ≤ 1s + SC-016 来源可追溯验收 |

---

## Complexity Tracking

> 未触发 — Constitution 全部 7 条均 ✅ 合规，无违反项需要豁免。

---

## Phase 0: Research 摘要

完整研究见 [research.md](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/research.md)。关键决策：

- **R1** Generation Engine → 复用 `ppt-master` 提 PR 加固 SVG→DrawingML→PPTX 适配（理由：项目方已有沉淀）
- **R2** Agent 框架 → 锁定 `AgentScope 2.0`，`ReActAgent` 处理 LLM 工具调用，`HarnessAgent` 包装多阶段流程
- **R3** 向量库 → MVP 阶段 `pgvector`（运维成本最低），GA 评估独立向量库
- **R4** 队列 → Redis Stream + FIFO 调度 + 5min 超时（FR-029）
- **R5** 风格契合度评分 → 三层客观指标（版式/配色/字体族） + 月度盲评（FR-028 / SC-002）
- **R6** PII 中间件 → Presidio 自定义规则（手机/邮箱/身份证/客户名），按 Q1 答案采用字段级处置
- **R7** 数据保留 → 样本/偏好长期，任务 180d（FR-026/027），归档走 MinIO 冷存储 + lifecycle policy
- **R8** SLA 监控 → 月度可用率采集自 `request_id` × `feature` 维度（M2-W3 上线仪表盘）
- **R9** US6 素材检索 → BM25 + 嵌入向量双路召回，归一化加权（0.4 / 0.4 / 0.2 视觉类型 boost）；用 pgvector 与 `material_search_index` 双表，触发器同步保持单一真值
- **R10** US6 草稿一致性 → 单写者锁（30min TTL）+ 乐观锁 `last_saved_revision` 双层防护；自动保存客户端 5s debounce，服务端 1s 内确认
- **R11** US6 导出溯源 → XMP / `customXml/item1.xml` 节点写入 `pptagent:sourceType` 等字段；不进 PPT 渲染层，仅供审计
- **R12** US6 样本解耦 → `ON DELETE SET NULL` 标记孤儿而非级联；孤儿素材默认隐藏，用户可手动清理
- **R13** US6 风格归一 → `StyleNormalizer` 工具（色板/字体/版式三轴）；失败降级为"未归一"原样插入 + 审计记录

---

## Phase 1: Design & Contracts 摘要

完整设计见：
- [data-model.md](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/data-model.md) — 6 实体、字段、状态机、关系
- [quickstart.md](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/quickstart.md) — 本地 5 分钟启动
- [contracts/openapi.yaml](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/contracts/openapi.yaml) — REST 接口契约（OpenAPI 3.1）
- [contracts/events.yaml](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/contracts/events.yaml) — WebSocket 实时事件契约
- [contracts/error-codes.yaml](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/contracts/error-codes.yaml) — RFC 7807 错误码

---

## Post-Design Constitution Re-check

| # | 原则 | 状态 | 备注 |
|---|------|------|------|
| **I** | 二开优先 | ✅ | `tools/svg2pptx.py` 显式 import `ppt-master`；`agents/` 显式继承 `AgentScope 2.0` 基类 |
| **II** | MVP 闭环 | ✅ | M1-M4 任务均与 spec FR 1:1 映射，无越界功能 |
| **III** | 可解释可控制 | ✅ | `trace_stage` 实体记录 4 阶段；`preference` 实体记录来源片段链 |
| **IV** | 数据安全前置 | ✅ | `db/models/` 分离 `raw_files` / `parse_results` / `embeddings` 三表；PII 中间件注册在中间件链首位 |
| **V** | 可观测可追溯 | ✅ | `observability.py` 强制 OTel + `request_id` / `user_id` / `feature` 三标签；关键事件结构化字段见 `events.yaml` |
| **VI** | 测试门禁 | ✅ | `tests/fixtures/samples/` 5 种真实样本；CI 6 阶段流水线在 `quickstart.md` §CI |
| **VII** | 版本与依赖 | ✅ | `pyproject.toml` 中 `ppt-master` 与 `agentscope` 以 `=={commit}` 形式锁定 |

> 全部 7 条 ✅，可进入 Phase 2（`/speckit.tasks`）。

---

**Plan Status**: ✅ Ready for Task Generation
**Recommended Next Command**: `/speckit.tasks` — 依据本 plan 与 [research.md](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/research.md) 生成可执行任务列表（按 [CORE]/[KB]/[EVOL]/[INFRA]/[QA]/[SEC] 标签分类）。
