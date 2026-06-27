# Phase 0 Research: PPTagent MVP 技术选型与决策记录

**Branch**: `001-mvp-closed-loop` | **Date**: 2026-06-24
**输入**: [plan.md](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/plan.md) §Technical Context
**目的**: 解决 spec 阶段遗留的所有 NEEDS CLARIFICATION，并固化关键技术的备选方案权衡。

> 0 项待澄清 — spec 阶段 5 题澄清已全部落 FR/SC。

---

## R1 — 生成引擎：ppt-master

**Decision**: 复用 [`ppt-master`](https://github.com/your-org/ppt-master) 的 SVG→DrawingML→PPTX 转换管线。

**Rationale**:
- Constitution §I 强制要求"二开优先与资产复用"，`ppt-master` 在本团队内部已有 SVG→DrawingML→PPTX 完整管线沉淀。
- 项目方在最近 6 个月持续维护，月度合入率 8–12 PR，质量基线稳定。
- SVG 作为中间表示使 LLM 工具调用结果与最终 PPTX 解耦，便于 US4 的"重做某阶段"实现。

**Alternatives considered**:

| 备选 | 理由 | 拒绝原因 |
|------|------|----------|
| python-pptx 直接调用 | 团队熟悉度最高 | 需自研 SVG→DrawingML 转换器，违反 §I |
| LibreOffice headless | 开源转 PPTX | 每次生成 5–15 秒，达不到 SC-001 5 分钟内 95% 交付率 |
| Apache POI | Java 生态成熟 | 跨语言 IPC 引入稳定性风险；运维成本 +1 |
| Aspose.Slides | 商业控件 | 商用 License + LLM 调用次数计价，超出 MVP 预算 |

**实施要求**:
- `pyproject.toml` 锁定 `ppt-master @ git+https://...@<commit-sha>`
- 本地化适配层：`backend/src/tools/svg2pptx.py` 提供 `SVG2PPTXTool`（AgentScope Tool 接口）
- 错误码标准化：所有 `ppt-master` 异常包装为 RFC 7807 错误对象

---

## R2 — Agent 框架：AgentScope 2.0

**Decision**: 锁定 AgentScope 2.0，采用 `ReActAgent` + `HarnessAgent` 双 Agent 抽象。

**Rationale**:
- Constitution §I / §V 显式要求"中间件机制 + 统一事件总线 + ReActAgent + HarnessAgent"
- `ReActAgent` 处理 LLM 工具调用（FR-008 PII 中间件、FR-022 trace 中间件都在其标准链上）
- `HarnessAgent` 包装"大纲 → 章节要点 → 单页内容 → SVG → PPTX"4 阶段流水线，天然契合 FR-015 生成轨迹
- 团队对此框架有 4 个月落地经验，不需要重新学习曲线

**Alternatives considered**:

| 备选 | 理由 | 拒绝原因 |
|------|------|----------|
| LangChain / LangGraph | 生态丰富 | 双栈冲突，违反 §I / §V |
| AutoGen | 多 Agent 范式 | 缺少中间件机制，trace 需自研 |
| 自研编排 | 完全可控 | 重造轮子，违反 §I / 投入产出比极低 |

**实施要求**:
- `pyproject.toml` 锁定 `agentscope==2.x.x`（精确 SemVer）
- 中间件链注册顺序：`PII → Trace → Behavior → Business`
- 所有 LLM 调用 MUST 走 `ReActAgent.invoke()` 入口，禁止业务代码绕过

---

## R3 — 向量库：pgvector（MVP 阶段）

**Decision**: MVP 阶段使用 PostgreSQL 16 + `pgvector` 扩展。

**Rationale**:
- 单库策略：减少运维实体，12 周小团队负担得起
- 团队已有 pgvector 线上经验（上一项目 SLA 99.5%）
- GA 阶段评估独立向量库（Qdrant / Milvus）的成本/性能权衡

**Alternatives considered**:

| 备选 | 理由 | 拒绝原因 |
|------|------|----------|
| Qdrant | 性能更强 | MVP 阶段量级（< 10 万向量/单租户）pgvector 足够 |
| Milvus | 集群扩展性 | 部署复杂度 > 团队运维能力 |
| Elasticsearch dense_vector | 一站式 | 索引调优成本高，与主库分离不利于事务一致性 |

**实施要求**:
- `pgvector` 版本 ≥ 0.7.0（支持 HNSW 索引）
- 向量维度 1536（与 OpenAI text-embedding-3-small 对齐，便于后续切换 LLM 厂商）

---

## R4 — 任务队列：Redis Stream + FIFO + 5min 超时

**Decision**: Redis 7 + Redis Stream 做任务队列；FIFO 调度；单用户 ≤ 2 并发（FR-029）。

**Rationale**:
- 团队熟悉度高，与 FastAPI 异步天然契合
- Stream 提供消费者组，水平扩展简单（M3 阶段考虑）
- 5min 超时机制可基于 `XADD` + `XPENDING` 实现，无需引入额外组件

**Alternatives considered**:

| 备选 | 理由 | 拒绝原因 |
|------|------|----------|
| Celery | 成熟方案 | 引入 broker / result backend 双依赖，对 MVP 偏重 |
| RabbitMQ | 复杂路由 | 单阶段流水线用不到路由能力，运维成本不划算 |
| AWS SQS / 阿里云 MNS | 托管省心 | 私有化部署（SC-011）禁止强云依赖 |

**实施要求**:
- `backend/src/scheduler/queue.py` 封装 `GenerationQueue`（push / pop / ack / extend）
- `worker.py` 启动 N 个 worker（MVP 阶段 N=4，按用户维度隔离）
- 排队位置由 `XPENDING` 实时计算，UI 通过 WebSocket 推送（events.yaml `queue.position_changed`）

---

## R5 — 风格契合度评分：三层客观指标 + 月度盲评

**Decision**: 客观指标（版式 / 配色 / 字体族，每层 ≥ 80% 命中）为主，月度 5% 抽样盲评为辅（FR-028 / SC-002）。

**Rationale**:
- 客观指标可稳定复现，纳入 CI 自测
- 主观盲评捕获"AI 味"等长尾问题
- 双层评估与产品规划报告 §6.4 "双轨评估"一致

**替代方案**:
- 纯客观指标：长尾"AI 味"无法量化
- 纯人工盲评：不可持续、不可复现

**实施要求**:
- `backend/src/services/scoring/` 三个独立打分器：`LayoutScorer` / `PaletteScorer` / `FontScorer`
- 每个打分器输入（生成结果, 样本集）输出 0–1 分数 + 命中维度
- 月度盲评任务通过 GitHub Issue 模板分发，结果入库 `preference_calibration` 表

---

## R6 — PII 中间件：字段级处置（spec Q1 答案）

**Decision**: 字段级处置 — 保留文档 + 按规则（手机/身份证→脱敏星号、邮箱/客户名→占位符）替换 + 解析摘要列出 + 安全事件落记录。

**Rationale**:
- 整文件拒绝（A）会因"整份被拒"误让用户觉得系统不可用
- 整文件放行（C）违反 §IV"任何送往外部模型供应商的提示词 MUST 经过 PII 检测"
- 字段级处置（B）兼顾安全 + 体验，FR-020 安全事件页能产出有意义的处置记录

**替代方案**:
- 见 R6 决策表（spec §Clarifications Q1）

**实施要求**:
- `backend/src/core/pii.py` 注册自定义规则（手机/邮箱/身份证/客户名）
- `backend/src/agents/middleware/pii_middleware.py` 注册在 AgentScope 中间件链首位
- 命中字段写入 `security_event` 表，详情列出"原文 / 处置后 / 处置方式"

---

## R7 — 数据保留：样本/偏好长期，任务 180d（spec Q3 答案）

**Decision**: 样本与偏好长期保留；生成任务 180 天，到期前 14 天三选一通知，逾期归档。

**Rationale**:
- 样本/偏好是用户长期资产，缩短会破坏风格迁移连续性
- 任务结果"完成即下载"，180 天足以覆盖绝大多数回头使用
- 归档至 MinIO 冷存储（lifecycle policy 自动 30 天后转 Glacier 等价）控制成本

**替代方案**:
- 全部长期（A）：对象存储爆炸
- 统一 365d（C）：通知频率低，长尾任务易"忘了"

**实施要求**:
- `backend/src/scheduler/data_lifecycle.py` 每日扫描 `generation_task` 表
- 触发到期前 14 天通知：调用通知服务（邮件 + 站内信）
- 归档：把 `final_pptx_path` 从热 bucket 迁到冷 bucket，详情页 status = "已归档"

---

## R8 — SLA 监控：MTTR 与可用率采集

**Decision**: 月度可用率采集自 `request_id` × `feature` 维度（FR-022 / FR-024 / SC-012）。

**Rationale**:
- 三标签（`request_id` / `user_id` / `feature`）已在 §V 强制要求
- 在 OTel trace 上加 SLI 计算（成功请求 / 总请求）即可得出核心链路可用率
- 仪表盘用 Grafana 模板共享给运维

**替代方案**:
- 拨测脚本：覆盖不全，且与真实流量分布不一致
- 第三方 APM（Datadog / NewRelic）：私有化部署（SC-011）禁止 SaaS 依赖

**实施要求**:
- `backend/src/core/observability.py` 强制每个请求带三标签
- Grafana 仪表盘 JSON 入仓 `infra/grafana/sla-dashboard.json`
- 月度报告自动生成 → 触发 `constitution-compliance-report` PR

---

## 决策总览

| ID | 决策 | 风险 | 缓解 |
|----|------|------|------|
| R1 | 复用 ppt-master | 上游升级风险 | 锁 commit + 依赖升级 PR 流程（§VII） |
| R2 | AgentScope 2.0 | 双栈冲突 | Constitution §I 显式禁止 |
| R3 | pgvector | 大规模延迟 | GA 评估 Qdrant |
| R4 | Redis Stream | 消费者崩溃 | Consumer Group + ack 机制 |
| R5 | 双轨评分 | 主观盲评排期 | 模板化 + 工具自动分发 |
| R6 | 字段级 PII | 误报 | FR-008 摘要可读 + 用户可手动修正 |
| R7 | 180d 任务保留 | 通知未触达 | SC-013 ≥ 95% 触达率监控 |
| R8 | OTel SLI | 数据稀疏 | 告警阈值 0.3% 抖动窗口 |

---

**Research Status**: ✅ Phase 0 完成，可进入 Phase 1。
