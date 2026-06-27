<!-- Sync Impact Report
  Version Change: 0.0.0 → 1.0.0
  Reason: Initial ratification for PPTagent project. Seven core principles established
    based on product feasibility report and secondary-development technical plan
    (AgentScope 2.0 + SVG-to-PPTX engine 二开).
  Principles Added (initial):
    - I.   二开优先与资产复用
    - II.  MVP 驱动与业务闭环
    - III. AI 生成可解释与可控制
    - IV.  数据安全与隐私前置
    - V.   Agent 行为可观测与可追溯
    - VI.  测试驱动与质量门禁
    - VII. 语义化版本与依赖锁定
  Sections Added:
    - 技术栈与架构约束
    - 开发工作流与里程碑
    - 合规与安全基线
  Templates to propagate:
    - .specify/templates/plan-template.md    → 需在 Constitution Check 中加入 I/IV/V/VI 条款
    - .specify/templates/spec-template.md    → 用户故事须覆盖知识库/生成/Agent进化三大主线
    - .specify/templates/tasks-template.md   → 任务分类须区分 [CORE] / [KB] / [EVOL] / [INFRA] / [QA]
  Deferred: 无
-->

# PPTagent Constitution

## Core Principles

### I. 二开优先与资产复用 (Second-Development-First)
PPTagent MUST 优先在成熟开源项目上做二次开发，而非从零自研。
- 核心生成链路 MUST 复用 SVG→DrawingML→PPTX 转换管线，禁止另起一套平行
  的 PPT 排版内核。
- 智能体编排 MUST 基于 `AgentScope 2.0` 的 `ReActAgent` + `HarnessAgent` 双
  Agent 抽象，禁止引入与现有事件总线/中间件机制冲突的替代框架。
- 任何新增的"自研"模块 MUST 在 spec/plan 中提供"为什么不能用现有 X"的明确
  取舍证据，并经过架构评审通过。
- 复用不等于"包进来即可"：被复用模块 MUST 经过本地化适配（接口收敛、错误
  标准化、可观测性接入），不允许在生产路径上以黑盒 SDK 形式直接调用。

### II. MVP 驱动与业务闭环 (MVP-Driven, Closed-Loop First)
所有交付 MUST 围绕"能跑通一个最小业务闭环"组织。
- MVP 定义：以"上传个人PPT → 一句话生成风格对齐的新PPT"为最小业务闭环。
- 12 周开发周期 MUST 严格按四个里程碑推进，禁止在前一里程碑未结案前开
  启下一里程碑的非基础设施任务：
  - M1（第 1–3 周）：生成链路（OrchestratorAgent + SVG2PPTXTool）
  - M2（第 4–6 周）：个人知识库（解析入库 + 双模检索）
  - M3（第 7–9 周）：Agent 进化引擎（BehaviorMiddleware + PreferenceExtractor）
  - M4（第 10–12 周）：去AI味打磨、定价落地、私有化Beta 发布
- 任何"看起来重要"但不能服务当前里程碑的功能 MUST 推迟或拒绝，避免沉没
  成本侵蚀 MVP。

### III. AI 生成可解释与可控制 (Explainable & Controllable AI)
PPT 生成涉及 LLM 创作与排版决策，每一步 MUST 可被用户理解、干预与回滚。
- 一次 PPT 生成 MUST 输出结构化的"生成轨迹"（大纲 → 章节要点 → 单页内
  容 → SVG → PPTX），每一步均可单独回看。
- LLM 工具调用 MUST 经由 `ReActAgent` 的标准中间件链，禁止业务代码绕过
  Agent 直接调用模型 API。
- 涉及"自动改写"或"自动调样式"的功能 MUST 提供"撤销/锁定原文"开关。
- 任何"去AI味"或"风格迁移"类功能 MUST 标注其依据的偏好来源（用户历史 /
  知识库样本 / 行业模板），不得伪装为"系统自动优化"。

### IV. 数据安全与隐私前置 (Data-Safety First)
用户上传的 PPT/PDF/Word 是高敏感资产，隐私与安全设计 MUST 前置，不允许
在 MVP 上线后再补。
- 知识库中的样本文件 MUST 在入库时即进行"原始文件 / 解析结果 / 嵌入向量"
  三类数据分离存储，并明确归属与生命周期。
- API 层 MUST 启用最小权限的 API Key 网关（读写分离、配额独立、日志脱敏）。
- 任何送往外部模型供应商的提示词 MUST 经过 PII（个人身份信息）检测中间
  件，自动去除手机号/邮箱/身份证号/客户名称等可识别字段。
- MVP 阶段禁止"默认开启模型微调 / 默认上传至第三方训练语料"等隐式行为。

### V. Agent 行为可观测与可追溯 (Observable & Traceable Agents)
Agent 编排是 PPTagent 的核心复杂度来源，必须具备生产级可观测性。
- 每次 Agent 执行 MUST 产出 trace 记录（中间件埋点统一进入 AgentScope 2.0
  的统一事件总线）。
- 关键事件 MUST 结构化输出：`tool_invocation`、`llm_call`、`ppt_render`、
  `preference_update`、`error_recover`，字段稳定可查询。
- 偏好提取（PreferenceExtractor）MUST 记录"来源片段 → 偏好规则"的映射
  链，禁止"凭空归纳"。
- 任何 LLM 调用 MUST 携带 `request_id` / `user_id` / `feature` 三个标签，方
  便按用户/功能回溯。

### VI. 测试驱动与质量门禁 (Test-First, Quality Gates)
复杂的多 Agent + 工具链系统极易隐性回归，测试门禁 MUST 强制。
- 任何新增的"工具"（Tool）MUST 在合并前具备：单元测试 + 契约测试 + 至
  少一条端到端集成路径。
- 涉及 PPTX 解析与生成的功能 MUST 用真实样本（非合成）做回归，样本库
  至少覆盖 5 种典型版式（汇报/培训/方案/数据/营销）。
- CI MUST 包含：lint → 单元 → 契约 → 端到端 → 安全扫描 → Token 预算校验
  六个阶段，任何阶段失败阻塞合并。
- 任何"调 LLM 提示词"的改动 MUST 同时更新"提示词 → 期望产出"对照用例。

### VII. 语义化版本与依赖锁定 (SemVer & Dependency Pinning)
PPTagent 处于快速迭代期，版本与依赖 MUST 严格可复现。
- 仓库版本遵循 `MAJOR.MINOR.PATCH` 三段语义化：MAJOR 表示破坏性架构变
  更（如更换核心生成引擎）；MINOR 表示新增里程碑能力；PATCH 表示 Bug
  修复与文案调整。
- 上游依赖（AgentScope 2.0 等）MUST 通过锁文件固定到具体 commit 或带
  校验和的 tag，禁止仅用 `latest` 或宽泛的 `^x.y`。
- 任何对上游依赖主干的升级 MUST 走"依赖升级 PR"流程：附 changelog 摘
  要、影响面评估、回滚方案。

## 技术栈与架构约束

**Frontend**：React 18 + TypeScript + Vite + Tailwind CSS + shadcn/ui 组件
库。前端 MUST 通过 OpenAPI 文档自动生成 TS 类型，禁止手写与后端字段不一
致的 DTO。

**Backend**：Python 3.11+ + FastAPI + Uvicorn + Pydantic v2。API 风格统一
RESTful + 长任务 WebSocket，错误码遵循 RFC 7807。

**Agent Framework**：AgentScope 2.0（已落地的 `ReActAgent` + `HarnessAgent`
+ 中间件机制 + 统一事件总线）。禁止引入 LangChain / AutoGen 等同质框架
造成双栈。

**Generation Engine**：SVG→DrawingML→PPTX 转换管线，以
`OrchestratorAgent` + `SVG2PPTXTool` 方式对接。

**Storage**：
- 结构化数据：PostgreSQL 16
- 向量检索：pgvector（短期）/ 独立向量库（GA 阶段评估）
- 对象存储：本地 MinIO（开发）/ S3 兼容存储（生产）
- 缓存：Redis 7

**Testing**：pytest（单元/契约）+ Playwright（端到端）+ Pact（服务契约）。
LLM 相关测试 MUST 使用模型回放（replay）模式以保证可重入。

**Observability**：OpenTelemetry + 结构化 JSON 日志 + 分布式 trace（jaeger
或同等方案）。

**Target Platform**：Linux 容器化部署（Docker + Kubernetes 预留），桌面端
形态由 Electron 包装为后续 GA 任务，不在 MVP 范围。

## 开发工作流与里程碑

**分支策略**：`main` 为发布分支，每个里程碑开一个长生命周期分支
（如 `m1-generation`），日常开发走短生命周期 `feature/*` 分支并通过 PR 合
入。

**Commit 规范**：Conventional Commits（`feat:` / `fix:` / `chore:` /
`refactor:` / `docs:` / `test:`），提交信息必须关联里程碑与用户故事 ID。

**PR 门禁**：lint + 单测 + 契约测试 + 安全扫描 + 至少一名代码评审者通过；
涉及核心生成链路或 Agent 行为必须额外有架构评审者。

**里程碑评审**：每个 M 结束必须输出"里程碑交付清单 + 演示录像 + 未完成项
与下阶段优先级" 三件套，方可解锁下一里程碑。

**私有化 Beta**：MVP 完成后 30 天内启动，候选客户数量 ≥ 3 家，回收的反馈
以"用户故事"形式进入 GA 阶段的需求池。

## 合规与安全基线

- 所有外部 API 调用 MUST 走统一网关，支持速率限制与熔断。
- 密钥管理使用 Vault 或云 KMS，禁止明文落盘。
- 涉及"导出用户数据"的功能 MUST 支持一键导出与一键删除（GDPR/个保法对
  齐）。
- 内部数据使用必须遵循"数据分级 + 最小可见"原则：客户原始文件不直接面
  向 LLM，仅以结构化摘要形式进入提示词。

## Governance
- 本 Constitution 是 PPTagent 项目的最高治理文件，所有 PR、spec、plan、
  task 评审 MUST 校验本文件条款。
- 修订流程：(1) 提交 issue 描述变更动因 → (2) 架构评审会讨论影响面 → (3)
  合并宪法 PR 并明确 SemVer bump 类型 → (4) 同步更新衍生模板（plan /
  spec / tasks）。
- 版本策略：MAJOR 变更需全员通告 + 迁移指南；MINOR/PATCH 变更在常规 PR
  流程中合并即可。
- 合规审查：每个里程碑 M 结束须附"宪法符合性自评表"，列出违反条款与豁
  免理由。
- 所有冲突以本文件优先；如出现与本文件冲突的临时约定，必须在两周内通过
  修订流程纳入本文件或显式撤销。

**Version**: 1.0.0 | **Ratified**: 2026-06-24 | **Last Amended**: 2026-06-24
