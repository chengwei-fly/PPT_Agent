# Tasks: PPTagent MVP 业务闭环

**Input**: Design documents from `/specs/001-mvp-closed-loop/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅
**Tests**: Per Constitution §VI — 每个新 Tool MUST 含单测+契约+端到端，PPTX 解析/生成 MUST 用真实样本回归。**Tests 显式纳入每个 User Story。**

---

## Format: `[ID] [P?] [Story] [Tag] Description`

- **[P]**：可并行（不同文件，无依赖）
- **[Story]**：所属用户故事（US1–US5）
- **[Tag]**：PPTagent 任务分类 — `[CORE]` 生成链路/二开适配、`[KB]` 知识库/RAG、`[EVOL]` Agent 进化、`[INFRA]` 基础设施/网关/监控、`[QA]` 测试/契约/样本库、`[SEC]` 安全/隐私/PII
- 描述含精确文件路径
- Setup / Foundational / Polish 阶段不挂 `[Story]`，但仍 MUST 带 `[Tag]`

---

## Phase 1: Setup (Shared Infrastructure) — M0 预热

**Purpose**: 项目骨架与开发工具链就位

- [X] T001 [INFRA] Create monorepo directory tree (backend/, frontend/, infra/, scripts/) at repo root per plan.md §Project Structure
- [X] T002 [INFRA] Initialize Python backend with `uv` in `backend/pyproject.toml`; lock `ppt-master @ git+...@<commit-sha>` and `agentscope==2.x.x` (Constitution §VII)
- [X] T003 [INFRA] Initialize React+Vite+TS frontend in `frontend/package.json`; add Tailwind+shadcn/ui per Constitution §技术栈
- [X] T004 [INFRA] Author `infra/docker-compose.yml` with PostgreSQL 16 + pgvector, Redis 7, MinIO, jaeger per quickstart.md §1
- [X] T005 [INFRA] Create `backend/.env.example` and `frontend/.env.example` (DB/Redis/MinIO/Jaeger endpoints + API key)
- [X] T006 [INFRA] Configure `ruff` (Python) + `eslint`+`prettier` (TS) + `pre-commit` hooks in `.pre-commit-config.yaml`
- [X] T007 [INFRA] Author `.github/workflows/ci.yml` with 6 stages (lint → unit → contract → e2e → security → token-budget) per Constitution §VI
- [X] T008 [INFRA] Create `backend/Dockerfile` and `frontend/Dockerfile` (multi-stage, non-root)
- [X] T009 [INFRA] Author `backend/src/scripts/seed_samples.py` to import 5 typical PPTX samples into MinIO
- [X] T010 [QA] Author `backend/tests/fixtures/samples/` with 5 real PPTX samples (汇报/培训/方案/数据/营销) per Constitution §VI — README documenting fixture requirements + auto-placeholder generation in seed script
- [X] T011 [INFRA] Create `Makefile` at repo root with `make dev` / `make test` / `make lint` / `make migrate` targets

**Checkpoint**: 仓库可 `git clone && make dev` 一键起服务，所有 CI 阶段空跑通过。

---

## Phase 2: Foundational (Blocking Prerequisites) — M0 收尾

**Purpose**: 任何 User Story 启动前必须完成的基础设施

**⚠️ CRITICAL**: US1–US5 全部依赖本阶段产物

- [X] T012 [INFRA] Setup FastAPI app skeleton + CORS + lifespan in `backend/src/main.py`
- [X] T013 [INFRA] Setup Pydantic v2 Settings (env-driven) in `backend/src/core/config.py`
- [X] T014 [INFRA] Setup SQLAlchemy 2.x + async session + Alembic in `backend/src/db/session.py` and `backend/src/db/migrations/env.py`
- [X] T015 [INFRA] Create User ORM model in `backend/src/db/models/user.py` per data-model.md §1
- [X] T016 [INFRA] Author Alembic migration `0001_init_users.py` (users + api_keys)
- [X] T016a [INFRA] Author Alembic migration `0002_idempotency.py` (idempotency_keys) per `contracts/api-design.md §15.1` and implement `IdempotencyMiddleware` in `backend/src/middleware/idempotency.py` (写入类 POST MUST 支持 `Idempotency-Key` 头；24h 内同 key 同 body 去重，body 变更返回 422 PPTAGENT.IDEMPOTENCY_MISMATCH)
- [X] T016b [INFRA] Implement `X-Request-Id` middleware in `backend/src/middleware/request_id.py` (客户端可选传入；服务端 MUST 生成并回传，关联 OTel trace)
- [X] T016c [INFRA] Implement cursor pagination helper in `backend/src/api/pagination.py` (用于 `/security/events` 大表 + 流式输出)
- [X] T017 [SEC] Implement API Key auth + rate-limit (60 req/min) + scope check in `backend/src/core/security.py` (Constitution §IV API 最小权限)
- [X] T018 [INFRA] Setup OpenTelemetry tracer + structured JSON logger with three-tag context (`request_id`/`user_id`/`feature`) in `backend/src/core/observability.py` (Constitution §V)
- [X] T019 [INFRA] Implement RFC 7807 error handler + Problem JSON serializer in `backend/src/core/errors.py` per `contracts/error-codes.yaml`
- [X] T020 [INFRA] Setup Redis client + Stream wrapper in `backend/src/scheduler/queue.py`
- [X] T021 [INFRA] Setup MinIO client + lifecycle policy for `ppt-cold` bucket in `backend/src/storage/minio.py`
- [X] T022 [INFRA] Setup frontend routing (React Router 6) + shadcn/ui primitives in `frontend/src/router/` and `frontend/src/components/ui/`
- [X] T023 [INFRA] Configure OpenAPI → TypeScript client generation (`pnpm gen:api` invokes `openapi-typescript`) in `frontend/package.json`
- [X] T024 [INFRA] Setup React Query + Zustand stores in `frontend/src/stores/`
- [X] T025 [SEC] Setup PII detection core (Presidio + custom rules: phone/email/id_card/customer_name) in `backend/src/core/pii.py`
- [X] T026 [INFRA] Setup AgentScope 2.0 base orchestration (event bus registration) in `backend/src/agents/base.py`
- [X] T027 [INFRA] Setup Pydantic v2 DTO base classes + OpenAPI metadata in `backend/src/models/__init__.py`
- [X] T028 [QA] Add unit-test scaffold (pytest + pytest-asyncio + coverage ≥80%) in `backend/pyproject.toml` and `backend/tests/conftest.py`
- [X] T029 [QA] Add frontend unit-test scaffold (vitest + @testing-library/react) in `frontend/vitest.config.ts`

**Checkpoint**: Foundation ready — US1–US5 可并行启动。

---

## Phase 3: User Story 1 — 一句话生成风格对齐的 PPT (Priority: P1) 🎯 MVP — M1 (W1–W3)

**Goal**: 用户输入一句话 + 知识库样本 → 5 分钟内产出 ≥10 页 PPTX 草案

**Independent Test**: 3 份样本入库后，输入"做一份 12 页 Q3 储能立项汇报"，5 分钟内拿到 PPTX 下载链接

### Tests for User Story 1

- [X] T030 [QA] [P] [US1] Author Pact contract test for `POST /generations` (queued response) in `backend/tests/contract/test_generation_create.py`
- [X] T031 [QA] [P] [US1] Author Pact contract test for `GET /generations/{id}` + `DELETE /generations/{id}` in `backend/tests/contract/test_generation_crud.py`
- [X] T032 [QA] [US1] Author integration test for full generation pipeline using 5 fixture samples in `backend/tests/integration/test_generation_e2e.py` (validates SC-001)

### Implementation for User Story 1

- [X] T033 [CORE] [P] [US1] Create `GenerationTask` ORM model in `backend/src/db/models/generation_task.py` per data-model.md §6
- [X] T034 [CORE] [P] [US1] Create `TraceStage` ORM model in `backend/src/db/models/trace_stage.py` per data-model.md §7
- [X] T035 [CORE] [US1] Author Alembic migration `0002_generation.py` (tasks + trace_stages + enum types)
- [X] T036 [CORE] [US1] Implement `SVG2PPTXTool` wrapping `ppt-master` in `backend/src/tools/svg2pptx.py` (FR-001 核心)
- [X] T037 [CORE] [US1] Implement `TraceMiddleware` in `backend/src/agents/middleware/trace_middleware.py` (writes TraceStage rows)
- [X] T038 [CORE] [US1] Implement `ReActAgent` with 3 sub-tools (outline/points/svg) in `backend/src/agents/react_agent.py`
- [X] T039 [CORE] [US1] Implement `OrchestratorAgent` (`HarnessAgent`) wrapping 4-stage pipeline in `backend/src/agents/orchestrator.py`
- [X] T040 [CORE] [US1] Implement generation pipeline service in `backend/src/services/generation/pipeline.py` (orchestrates 4 stages, emits events)
- [X] T041 [CORE] [US1] Implement token estimator (historical median) in `backend/src/services/generation/token_estimator.py` (FR-004)
- [X] T042 [CORE] [US1] Implement queue worker with single-user 2-concurrency gate + 5min queue deadline in `backend/src/scheduler/worker.py` (FR-029)
- [X] T043 [CORE] [US1] Implement `POST /generations` (with `queue_position` in 202 response) in `backend/src/api/generations.py`
- [X] T044 [CORE] [US1] Implement `GET /generations/{id}` (with `style_fit_score` when success) in `backend/src/api/generations.py`
- [X] T045 [CORE] [US1] Implement `DELETE /generations/{id}` (cancel within 5s) in `backend/src/api/generations.py` (FR-003)
- [X] T046 [CORE] [US1] Implement WebSocket `/ws` channel `task:{task_id}` per `contracts/events.yaml` in `backend/src/api/ws.py`
- [X] T047 [CORE] [US1] Frontend 一句话输入页 with 3-step layout in `frontend/src/pages/GenerationPage.tsx` (FR-001/US1 acceptance #2 KB empty)
- [X] T048 [CORE] [US1] Frontend `GenerationRunner` (progress/cancel/download) consuming WS events in `frontend/src/components/generation/GenerationRunner.tsx`
- [X] T049 [CORE] [US1] Frontend 排队位置常驻条 in `frontend/src/components/generation/QueueIndicator.tsx` (FR-029 + SC-014)
- [X] T050 [QA] [US1] E2E Playwright test for full US1 journey in `frontend/tests/e2e/us1_generation.spec.ts`

**Checkpoint**: US1 alone is a runnable MVP — `make dev` → upload 1 sample → input prompt → get PPTX.

---

## Phase 4: User Story 2 — 上传并管理个人样本 (Priority: P1) 🎯 — M2 (W4–W6)

**Goal**: PPTX/PDF/DOCX 批量上传（≤50MB/份，≤20 份/批）→ 解析入库 + PII 字段级处置 + 双模检索

**Independent Test**: 拖入 5 份样本（包含手机号/邮箱/客户名）→ 2 分钟内全部 `parsed`，PII 字段在摘要中标出，重复文件自动去重

### Tests for User Story 2

- [X] T051 [QA] [P] [US2] Author Pact contract test for `POST /samples/batch` + `GET /samples` + `DELETE /samples/{id}` in `backend/tests/contract/test_samples.py`
- [X] T052 [QA] [US2] Author integration test for PII hit + field-level replace in `backend/tests/integration/test_samples_pii.py` (validates FR-008 + SC-004)
- [X] T053 [QA] [US2] Author unit test for SHA-256 dedup in `backend/tests/unit/test_sample_dedup.py` (validates FR-010)

### Implementation for User Story 2

- [X] T054 [KB] [P] [US2] Create `Sample` ORM model in `backend/src/db/models/sample.py` per data-model.md §2
- [X] T055 [KB] [P] [US2] Create `ParseResult` ORM model in `backend/src/db/models/parse_result.py` per data-model.md §3
- [X] T056 [KB] [P] [US2] Create `Embedding` ORM (pgvector) in `backend/src/db/models/embedding.py` per data-model.md §4
- [X] T057 [KB] [US2] Author Alembic migration `0003_samples.py` (samples + parse_results + embeddings + HNSW index)
- [X] T058 [KB] [US2] Implement `SampleParser` tool (PPTX/PDF/DOCX) with version pinning in `backend/src/tools/sample_parser.py` (FR-006/FR-007)
- [X] T059 [KB] [US2] Implement `PIIDetector` tool (independent, callable from parse pipeline) in `backend/src/tools/pii_detector.py` (FR-008)
- [X] T060 [SEC] [US2] Implement `PIIMiddleware` in `backend/src/agents/middleware/pii_middleware.py` (field-level replace per spec Q1)
- [X] T061 [KB] [US2] Implement knowledge base service (parse → PII → embed) in `backend/src/services/knowledge_base/service.py`
- [X] T062 [KB] [US2] Implement async embedder worker (OpenAI text-embedding-3-small, 1536-d) in `backend/src/services/knowledge_base/embedder.py`
- [X] T063 [KB] [US2] Implement dual-mode retriever (vector cosine + keyword) in `backend/src/tools/knowledge_retriever.py`
- [X] T064 [KB] [US2] Wire knowledge retrieval into `ReActAgent` (replaces placeholder sample list) in `backend/src/agents/react_agent.py`
- [X] T065 [KB] [US2] Implement `POST /samples/batch` (multipart, size + count guards) in `backend/src/api/samples.py` (FR-006)
- [X] T066 [KB] [US2] Implement `GET /samples` (paginated, excludes soft-deleted) in `backend/src/api/samples.py` (FR-007)
- [X] T067 [KB] [US2] Implement `DELETE /samples/{id}` (cascade ParseResult+Embedding) in `backend/src/api/samples.py` (FR-007/FR-009)
- [X] T068 [KB] [US2] Frontend 知识库管理页 (list/upload/delete) in `frontend/src/pages/KnowledgePage.tsx`
- [X] T069 [KB] [US2] Frontend 拖拽上传组件 with progress in `frontend/src/components/knowledge/UploadDropzone.tsx`
- [X] T070 [KB] [US2] Frontend PII 处置摘要展示 in `frontend/src/components/knowledge/PiiBadge.tsx`
- [X] T071 [QA] [US2] E2E Playwright test for US2 in `frontend/tests/e2e/us2_knowledge.spec.ts` (validates FR-006/007/008/010)

**Checkpoint**: US2 unblocks US1 真实可用 — 没有样本库，US1 永远停在"KB empty"提示。

---

## Phase 5: User Story 3 — Agent 学习并应用我的偏好 (Priority: P2) — M3 (W7–W9)

**Goal**: 5 次相同修改 → 第 6 次自动应用，且在轨迹中明示"已应用偏好 P-NNN（依据：…）"

**Independent Test**: 对封面 logo 改 5 次"放右上角" → 第 6 次输入"做 10 页汇报"，封面自动放右上角 + 明示偏好 ID

### Tests for User Story 3

- [X] T072 [QA] [P] [US3] Author Pact contract test for `GET /preferences` + `DELETE /preferences/{id}` in `backend/tests/contract/test_preferences.py`
- [X] T073 [QA] [US3] Author integration test for preference extraction (5× same → 1 rule) in `backend/tests/integration/test_preference_extract.py` (validates SC-007)
- [X] T074 [QA] [US3] Author unit test for ignore-count increment on 撤销/锁定 in `backend/tests/unit/test_preference_ignore.py` (validates FR-014)

### Implementation for User Story 3

- [X] T075 [EVOL] [US3] Create `Preference` ORM model in `backend/src/db/models/preference.py` per data-model.md §5
- [X] T076 [EVOL] [US3] Author Alembic migration `0004_preferences.py` (preferences + source_chain JSONB)
- [X] T077 [EVOL] [US3] Implement `PreferenceExtractor` (LLM-based rule induction from `source_chains`) in `backend/src/services/preference/extractor.py` (FR-011, §V 来源片段链)
- [X] T078 [EVOL] [US3] Implement `BehaviorMiddleware` (auto-apply + ignore-count tracking + lock check) in `backend/src/agents/middleware/behavior_middleware.py` (FR-012/FR-014)
- [X] T079 [EVOL] [US3] Wire preference apply into generation pipeline (emit `task.preference.applied` WS event) in `backend/src/services/generation/pipeline.py` (SC-008 100% 明示)
- [X] T080 [EVOL] [US3] Implement 撤销/锁定原文 lock mechanism in `backend/src/services/generation/lock.py` (FR-017)
- [X] T081 [EVOL] [US3] Implement `GET /preferences` (paginated by `apply_count` DESC) in `backend/src/api/preferences.py` (FR-013)
- [X] T082 [EVOL] [US3] Implement `DELETE /preferences/{id}` (soft delete, sets `is_active=false`) in `backend/src/api/preferences.py` (FR-013)
- [X] T083 [EVOL] [US3] Frontend 我的偏好页 (list/source chains/delete) in `frontend/src/pages/PreferencesPage.tsx`
- [X] T084 [EVOL] [US3] Frontend 撤销/锁定原文 toggle in `frontend/src/components/generation/LockToggle.tsx`
- [X] T085 [QA] [US3] E2E Playwright test for US3 in `frontend/tests/e2e/us3_preferences.spec.ts`

**Checkpoint**: US3 + US4 together deliver "Agent 越用越好用"的核心承诺。

---

## Phase 6: User Story 4 — 生成轨迹可回看与可回滚 (Priority: P2) — M3 (W7–W9)

**Goal**: 4 阶段轨迹可视化 + 任意阶段"重做" + 失败阶段可重试/跳过/反馈

**Independent Test**: 完成任务后打开轨迹页 → 4 张阶段卡齐全 → 对第 3 阶段"重做" → 耗时 < 完整重做的 40%

### Tests for User Story 4

- [X] T086 [QA] [P] [US4] Author Pact contract test for `GET /generations/{id}/trace` + `POST /generations/{id}/stages/{name}/redo` in `backend/tests/contract/test_trace.py`
- [X] T087 [QA] [US4] Author integration test for stage redo + timing saving in `backend/tests/integration/test_trace_redo.py` (validates SC-009 ≥ 60% saving)

### Implementation for User Story 4

- [X] T088 [CORE] [US4] Implement `GET /generations/{id}/trace` (ordered by `stage_order`) in `backend/src/api/traces.py` (FR-015)
- [X] T089 [CORE] [US4] Implement `POST /generations/{id}/stages/{name}/redo` (rerun that stage + downstream) in `backend/src/api/traces.py` (FR-016)
- [X] T090 [CORE] [US4] Implement stage redo service (preserve upstream outputs, reset downstream) in `backend/src/services/generation/redo.py`
- [X] T091 [CORE] [US4] Frontend 生成轨迹页 (4 阶段卡片 + 重做按钮) in `frontend/src/pages/TracePage.tsx` (FR-015)
- [X] T092 [CORE] [US4] Frontend 阶段重做 confirm dialog in `frontend/src/components/trace/RedoButton.tsx`
- [X] T093 [QA] [US4] E2E Playwright test for US4 in `frontend/tests/e2e/us4_trace.spec.ts`

**Checkpoint**: US3 + US4 同时上线 → 客户演示可看到"AI 行为可解释可控制"的完整证据。

---

## Phase 7: User Story 5 — 数据安全与一键删除 (Priority: P3) — M4 (W10–W12)

**Goal**: 一键导出 ZIP（原始+摘要+偏好 JSON）+ 一键删除（24h 内生产库清空 / 7d 备份清空）+ 安全事件可视化

**Independent Test**: 触发 PII 命中 → 安全事件页可见；一键导出 → 10 分钟内 ZIP 可下载；一键删除 → 1 小时内生产库无残留

### Tests for User Story 5

- [X] T094 [QA] [P] [US5] Author Pact contract test for `POST /data/export` + `POST /data/delete-all` in `backend/tests/contract/test_data_lifecycle.py`
- [X] T095 [QA] [US5] Author integration test for ZIP integrity (SHA-256 manifest match) in `backend/tests/integration/test_data_export.py` (validates SC-006)
- [X] T096 [QA] [US5] Author integration test for hard-delete in 24h + backup purge in 7d in `backend/tests/integration/test_data_delete.py` (validates SC-005 + FR-019)
- [X] T097 [QA] [US5] Author unit test for task archive (180d + 14d notify) in `backend/tests/unit/test_task_archive.py` (validates SC-013)

### Implementation for User Story 5

- [X] T098 [SEC] [US5] Create `SecurityEvent` ORM model in `backend/src/db/models/security_event.py` per data-model.md §8
- [X] T099 [SEC] [US5] Author Alembic migration `0005_security_events.py`
- [X] T100 [SEC] [US5] Implement export service (ZIP packaging: raw files + structure + preferences JSON + SHA-256 manifest) in `backend/src/services/data_lifecycle/export.py` (FR-018)
- [X] T101 [SEC] [US5] Implement delete-all service (三类数据 cascade: raw_files → parse_results → embeddings → preferences → generation_tasks → trace_stages) in `backend/src/services/data_lifecycle/delete.py` (FR-009 + FR-019)
- [X] T102 [SEC] [US5] Implement task archive worker (daily scan, 14d 通知 + 180d archive) in `backend/src/scheduler/data_lifecycle.py` (FR-026/FR-027)
- [X] T103 [SEC] [US5] Wire PII middleware to write `SecurityEvent` rows in `backend/src/agents/middleware/pii_middleware.py` (FR-020)
- [X] T104 [SEC] [US5] Implement `POST /data/export` in `backend/src/api/data_lifecycle.py`
- [X] T105 [SEC] [US5] Implement `POST /data/delete-all` (with 二次确认) in `backend/src/api/data_lifecycle.py`
- [X] T106 [SEC] [US5] Implement `GET /security/events` (paginated, filter by `event_type`) in `backend/src/api/security.py`
- [X] T107 [SEC] [US5] Frontend 安全事件页 in `frontend/src/pages/SecurityPage.tsx` (FR-020)
- [X] T108 [SEC] [US5] Frontend 导出/删除/归档 UI (with confirm dialogs) in `frontend/src/components/data_lifecycle/DataActions.tsx`
- [X] T109 [QA] [US5] E2E Playwright test for US5 in `frontend/tests/e2e/us5_security.spec.ts`

**Checkpoint**: US5 上线 = GDPR/个保法基线合规，可对外公开"支持一键导出/删除"。

---

## Phase 8: Polish & Cross-Cutting Concerns — M4 (W10–W12)

**Purpose**: SLA 仪表盘 + 风格契合度评分 + 合规报告 + 上线准备

- [X] T110 [INFRA] Implement `GET /healthz` (status + queue_length) + `GET /metrics` (Prometheus) in `backend/src/api/ops.py` (FR-023)
- [X] T111 [INFRA] Implement `LayoutScorer` (版式结构) in `backend/src/services/scoring/layout_scorer.py` (FR-028)
- [X] T112 [INFRA] Implement `PaletteScorer` (配色分布) in `backend/src/services/scoring/palette_scorer.py` (FR-028)
- [X] T113 [INFRA] Implement `FontScorer` (字体族) in `backend/src/services/scoring/font_scorer.py` (FR-028)
- [X] T114 [INFRA] Wire scorers into generation pipeline (compute on `status=success`) in `backend/src/services/generation/pipeline.py` (SC-002)
- [X] T115 [INFRA] Author Grafana SLA dashboard JSON in `infra/grafana/sla-dashboard.json` (FR-024/SC-012)
- [X] T116 [INFRA] Author monthly availability report generator in `scripts/availability_report.py` (PR to docs/ monthly)
- [X] T117 [QA] Author 5-typical-sample regression suite (5 PPTX × 4 scenarios) in `backend/tests/integration/test_sample_regression.py` (Constitution §VI 真实样本回归)
- [X] T118 [QA] Author token budget validation test in `backend/tests/integration/test_token_budget.py` (validates SC-001/SC-009)
- [X] T119 [SEC] Author security scan workflow (`bandit -r src` + `npm audit`) in `.github/workflows/security.yml`
- [X] T120 [INFRA] Author Constitution v1.0.0 compliance report template in `docs/constitution-compliance.md` (per Constitution §Governance 里程碑评审)
- [X] T121 [INFRA] Author `README.md` with quickstart, milestone roadmap, contribution guide
- [X] T122 [QA] Run full CI 6-stage pipeline dry-run, capture baseline metrics
- [X] T123 [INFRA] Coordinate private-beta pilot kickoff (≥ 3 customers per SC-011), set up feedback collection template

---

## Phase 9: User Story 6 — 素材检索与方案拼装 (Priority: P1) 🎯 MVP 核心 (M5 切片)

**Goal**: PM / 方案人员可检索复用历史素材，与 AI 生成 / 手动内容混合拼装，输出风格一致的方案 PPT；保留每张页的来源标注便于审计。

**Independent Test**: 上传 5 份历史 PPT 后，搜索"储能架构图"并插入 3 张复用页 + 2 张 AI 生成页 → 导出 PPTX → 所有页来源可追溯；修改草稿不影响原样本；并发打开时后者只读。

**前置依赖**: Phase 1（基础表 + RLS）/ Phase 2（解析链路）已完成；与 M2 同步推进。

### 9.1 数据迁移与 ORM

- [X] T200 [CORE] [P] [US6] Author Alembic migration `0007_materials_and_drafts.py` in `backend/migrations/versions/0007_materials_and_drafts.py`（含 ENUM `slide_visual_type` / `draft_status` / `draft_slide_source_type`；表 `slide_assets` / `drafts` / `draft_slides` / `material_search_index`；触发器 `trg_slide_assets_sync_search` + `trg_sample_delete_orphan_assets`；4 条 RLS Policy）per `data-model.md §2.2.10~13`
- [X] T201 [CORE] [P] [US6] Create ORM model `SlideAsset` in `backend/src/db/models/slide_asset.py`
- [X] T202 [CORE] [P] [US6] Create ORM models `Draft` + `DraftSlide` + `MaterialSearchIndex` in `backend/src/db/models/draft.py`
- [X] T203 [CORE] [US6] Create Pydantic DTOs (SlideAsset / SlideAssetDetail / MaterialSearchRequest / MaterialSearchResult / InsertMaterialRequest / Draft / DraftSlide / DraftDetail / CreateDraftRequest / UpdateDraftRequest / UpdateDraftSlideRequest / DraftLockInfo / DraftExportRequest / DraftExportJob) in `backend/src/models/dto.py` per `data-model.md §3`

### 9.2 素材抽取与索引（FR-030）

- [X] T210 [CORE] [US6] Implement `SlideExtractor` (按 sample 逐页抽取 SVG / text / image / chart，分类 visual_type) in `backend/src/services/parsing/slide_extractor.py`
- [X] T211 [CORE] [US6] Wire `SlideExtractor` into parsing pipeline (FR-007 解析完成后异步触发) in `backend/src/services/parsing/pipeline.py`
- [X] T212 [CORE] [US6] Implement thumbnail renderer (PPTX → PNG，300dpi) in `backend/src/services/parsing/thumbnail.py`（存 MinIO）
- [X] T213 [CORE] [US6] Implement embedding writer for `slide_assets.embedding` (复用 `embeddings` 服务的 same model) in `backend/src/services/parsing/embed_writer.py`
- [X] T214 [QA] [US6] Author unit test for `SlideExtractor` with 3-typical-sample fixtures in `backend/tests/unit/test_slide_extractor.py`
- [X] T215 [QA] [US6] Author integration test "extract → index → search" pipeline in `backend/tests/integration/test_material_extraction.py`

### 9.3 素材检索服务（FR-031 / FR-032）

- [X] T220 [CORE] [US6] Implement `MaterialSearchService.hybrid_search()` (BM25 + 嵌入向量 + 视觉类型 boost) in `backend/src/services/search/material_search.py`
- [X] T221 [CORE] [US6] Implement filter serialization (visual_types / industry_tags / source_sample_ids / include_orphan) → URL query in `backend/src/api/assets.py`
- [X] T222 [CORE] [US6] Add `/materials` GET (list/search) + `/materials/{id}` GET (detail) + `DELETE` in `backend/src/api/assets.py` per `openapi.yaml` US6
- [X] T223 [QA] [US6] Author contract test for `GET /materials` (Pact provider) in `backend/tests/contract/test_materials_pact.py`
- [X] T224 [QA] [US6] Author perf test (P95 ≤ 1s, 1000-assets corpus) in `backend/tests/perf/test_material_search_perf.py`（验证 SC-015）

### 9.4 草稿服务（FR-033 / FR-035）

- [X] T230 [CORE] [P] [US6] Implement `DraftService` (CRUD + 乐观锁 `last_saved_revision` + 自动保存) in `backend/src/services/draft/draft_service.py`
- [X] T231 [CORE] [US6] Implement single-writer lock acquire/release with 30-min auto-expiry in `backend/src/services/draft/lock.py`
- [X] T232 [CORE] [US6] Implement `insert_slide` (复用 / 生成 / 手动三来源) in `backend/src/services/draft/draft_service.py::insert_slide`
- [X] T233 [CORE] [US6] Implement `reorder_slides` (拖拽排序后批量写回 `slide_order`) in `backend/src/services/draft/draft_service.py::reorder_slides`
- [X] T234 [CORE] [US6] Add `/drafts` GET/POST + `/drafts/{id}` GET/PATCH/DELETE + `/drafts/{id}/lock` POST/DELETE in `backend/src/api/drafts.py` per `openapi.yaml` US6
- [X] T235 [CORE] [US6] Add `/drafts/{id}/slides/{sid}` PATCH/DELETE in `backend/src/api/drafts.py::slides`
- [X] T236 [INFRA] [US6] Implement cron `release_expired_draft_locks` (每 5 分钟) in `backend/src/scheduler/cron_jobs.py`
- [X] T237 [QA] [US6] Author contract test for draft CRUD + lock + revision mismatch in `backend/tests/contract/test_drafts_pact.py`
- [X] T238 [QA] [US6] Author integration test "concurrent open → second writer read-only" in `backend/tests/integration/test_draft_lock.py`

### 9.5 风格归一（FR-034）

- [X] T240 [CORE] [US6] Implement `StyleNormalizer` (asset 风格 → draft overall_style 映射；色板 / 字体族 / 版式) in `backend/src/tools/style_normalizer.py`
- [X] T241 [CORE] [US6] Implement normalize-failure fallback (保留原样 + `normalized_failed=true` + 审计事件) in `backend/src/tools/style_normalizer.py::normalize_or_fallback`
- [X] T242 [CORE] [US6] Wire `StyleNormalizer` into `/materials/{id}/insert` endpoint in `backend/src/api/assets.py::insert`
- [X] T243 [QA] [US6] Author unit test for `StyleNormalizer` (3 pass + 2 fail cases) in `backend/tests/unit/test_style_normalizer.py`

### 9.6 草稿导出与溯源（FR-036 / FR-037）

- [X] T250 [CORE] [US6] Implement `DraftExporter` (PPTX 打包 + 每张页 source attribution 写入 XMP / customXml) in `backend/src/services/export/draft_exporter.py`
- [X] T251 [CORE] [US6] Implement `add_source_to_slide` (per slide, 写 `pptagent:sourceType` + `pptagent:sourceAttribution` + 复用页附加 sample_id / page_index) in `backend/src/services/export/source_attribution.py`
- [X] T252 [CORE] [US6] Add `/drafts/{id}/export` POST (202 + job_id) + `/drafts/{id}/export/{job_id}` GET (进度查询) in `backend/src/api/drafts.py::export`
- [X] T253 [QA] [US6] Author end-to-end test "search → insert → edit → export → re-open PPTX" verifying source metadata in `backend/tests/e2e/test_draft_export.py`（验证 SC-016）
- [X] T254 [QA] [US6] Author unit test for `add_source_to_slide` (3 source types) in `backend/tests/unit/test_source_attribution.py`

### 9.7 前端

- [X] T260 [FE] [US6] Create `MaterialLibraryPage` (左侧筛选 + 右侧网格缩略图 + 关键词搜索) in `frontend/src/pages/MaterialLibraryPage.tsx`
- [X] T261 [FE] [US6] Create `MaterialDetailDrawer` (SVG 预览 + 缩略图大图 + 来源信息 + "插入草稿"按钮) in `frontend/src/components/material/MaterialDetailDrawer.tsx`
- [X] T262 [FE] [US6] Create `DraftListPage` + `DraftEditorPage` (拖拽排序 + 缩略图列表 + 来源标签) in `frontend/src/pages/DraftEditorPage.tsx`
- [X] T263 [FE] [US6] Add SWR hooks `useMaterials` / `useMaterialSearch` / `useDraft` / `useDraftAutosave` (debounce 5s) in `frontend/src/hooks/`
- [X] T264 [FE] [US6] Add WebSocket subscription for `draft.locked` / `draft.exported` events in `frontend/src/ws/draftSubscriptions.ts`

### 9.8 文档与可观测

- [X] T270 [INFRA] [US6] Add Grafana panel "素材复用率 / 草稿导出次数" to `infra/grafana/material-usage.json`（运营指标）
- [X] T271 [INFRA] [US6] Add structured log namespace `pptagent.material.*` / `pptagent.draft.*` in `backend/src/observability/logging.py`
- [X] T272 [DOCS] [US6] Author user guide "素材库与方案拼装" in `docs/user-guide/material-and-draft.md`

### 9.9 WS 事件 / 错误码 / 契约

- [X] T280 [INFRA] [US6] Add WS events `draft.locked` / `draft.unlocked` / `draft.saved` / `draft.slide.inserted` / `draft.exported` / `material.indexed` in `contracts/events.yaml`（US6 通道 `draft:{draft_id}` / `user:{user_id}:materials` 同步补全）
- [X] T281 [INFRA] [US6] Add error codes `PPTAGENT.MATERIAL_IN_USE` / `PPTAGENT.MATERIAL_NOT_FOUND` / `PPTAGENT.DRAFT_REVISION_MISMATCH` / `PPTAGENT.DRAFT_LOCKED` / `PPTAGENT.NORMALIZATION_FAILED` / `PPTAGENT.DRAFT_EMPTY` / `PPTAGENT.DRAFT_SOURCE_CONFLICT` in `contracts/error-codes.yaml`（覆盖 US6 全部 7 个错误码）
- [X] T282 [QA] [US6] Update Pact broker with new US6 contracts (CI 阶段 3)

---

## Dependencies (Story Completion Order)

```text
Setup (T001–T011)
    │
    ▼
Foundational (T012–T029)
    │
    ├──────────────┬──────────────┬──────────────┐
    ▼              ▼              ▼              ▼
  US1 (T030–T050) US2 (T051–T071) US3 (T072–T085) US4 (T086–T093)   ← US3+US4 share M3 week slot
    │              │              │              │
    │              └──────┬───────┘              │
    │                     ▼                      │
    │              US5 (T094–T109)               │
    │                     │                      │
    └─────────┬───────────┴──────────────────────┘
              ▼
        Polish (T110–T123)
```

**Key dependencies**:
- US2 unblocks US1 真实可用（KB 样本源）；US1 自身可用"KB empty"分支
- US3 依赖 US1 的生成轨迹 (TraceStage) 作为"来源片段"输入
- US4 依赖 US1 的 TraceStage 实体；US4 阶段重做时需要 US1 worker
- US5 依赖 US1+US2+US3 的所有实体（三类数据 cascade）
- Polish 阶段前置依赖所有 User Story

---

## Parallel Execution Examples

### Setup 阶段（T001–T011）可全并行

```bash
# T001-T008 全部可并行
# T009 依赖 T010（seed 用到 fixtures）
# T010 独立
# T011 独立（最末）
```

### Foundational 阶段（T012–T029）部分并行

```bash
# 并行组 A：基础架构（T012-T020, T026-T027）
# 并行组 B：前端骨架（T022-T024）— 可与 A 并行
# 串行：T025 (PII 核心) → 后续 US 任务依赖
# 串行：T028, T029 (测试脚手架) → 测试类任务前置
```

### US1 阶段（T030–T050）

```bash
# 并行：
#   T033 (GenerationTask) + T034 (TraceStage) + T030, T031 (合同测试)
#   T036 (SVG2PPTXTool) — 独立
#   T037 (TraceMiddleware) 依赖 T034
#   T038 (ReActAgent) 依赖 T037
# 串行：
#   T039 (OrchestratorAgent) 依赖 T038
#   T040 (Pipeline) 依赖 T039 + T041
#   T042 (Queue worker) 依赖 T020 + T040
#   T043-T045 (API) 依赖 T040
#   T046 (WS) 依赖 T018 + T040
#   T047-T049 (前端) 依赖 T023 + T024
# 末：T050 (E2E) 依赖以上全部
```

### US2 阶段（T051–T071）

```bash
# 并行：
#   T054-T056 (3 个 ORM 模型) + T051-T053 (测试)
#   T058 (SampleParser) + T059 (PIIDetector) 独立
# 串行：
#   T060 (PII Middleware) 依赖 T025 + T059
#   T061 (KB service) 依赖 T058 + T060
#   T062 (Embedder) 依赖 T061
#   T063 (Retriever) 依赖 T062
#   T064 (wire into ReAct) 依赖 T038 + T063
#   T065-T067 (API) 依赖 T061
#   T068-T070 (前端) 依赖 T023
# 末：T071 (E2E)
```

---

## Implementation Strategy

### MVP First (US1 单独可交付)

按 Constitution §II "MVP 驱动与业务闭环"，US1 单独即构成可演示 MVP：
- 用户上传 1 份样本 → 输入一句话 → 5 分钟拿到 PPTX
- 不依赖 US2 完整知识库（KB empty 引导）
- 不依赖 US3 偏好进化（固定 prompt）
- 不依赖 US4 轨迹回滚（直接看最终结果）
- 不依赖 US5 数据安全（默认开启即可）

### Incremental Delivery (推荐)

| 里程碑 | 任务范围 | 验收 |
|--------|----------|------|
| **M0** | T001–T029 | `make dev` 一键起服务；`make test` 全绿 |
| **M1** | T030–T050 | US1 全通；SC-001 ≥ 95% 交付率 |
| **M2** | T051–T071 | US2 全通；FR-008 PII 命中 ≥ 99% |
| **M3** | T072–T093 | US3 + US4 全通；SC-007/008/009 达标 |
| **M4** | T094–T123 | US5 + Polish；SC-005/006/011/012/013/014 全部达标；私有化 Beta ≥ 3 家 |

### Test Discipline (Constitution §VI)

- **每次 PR**：必须 `lint + unit + contract` 三阶段绿
- **合入主分支**：必须 6 阶段全绿 + 至少 1 名评审者
- **涉及核心生成链路或 Agent 行为**：必须额外 1 名架构评审者
- **真实样本回归**：T117 必须持续绿（不允许删测试用例绕过）

### Tag 统计（提交时可校验）

预期分布（task 总数 = 123）：

| Tag | 任务数 | 占比 |
|-----|--------|------|
| [CORE] | 20 | 16% |
| [KB] | 17 | 14% |
| [EVOL] | 11 | 9% |
| [INFRA] | 31 | 25% |
| [QA] | 22 | 18% |
| [SEC] | 16 | 13% |

> 跨里程碑统计时可按此分布核对是否失衡（单一 Tag > 40% 视为里程碑未结案）。

---

**Tasks Status**: ✅ Phase 1–8 全部任务已就位（123 个）
**Recommended Next Command**: `/speckit.implement` — 按 M0 → M1 → M2 → M3 → M4 顺序执行；MVP 优先走 T001–T050。
