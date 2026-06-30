# PPT-master 对标分析

> 目标：系统对比 GitHub 项目 [`hugohe3/ppt-master`](https://github.com/hugohe3/ppt-master) 与本仓库 `PPT_Agent` 的能力差异，提炼可借鉴点与差异化护城河，为后续迭代提供决策依据。
> 范围：基于 `ppt-master` README、官方文档与本仓库 `M0–M5` 已交付能力，事实层信息以源码 / 文档为准。

---

## 1. 项目画像速览

| 维度 | **PPT-master** | **PPT_Agent（本项目）** |
| --- | --- | --- |
| 形态 | 跑在 AI IDE 内的"工作流 Skill"（Claude Code / Cursor / VS Code Copilot / Trae 等） | 完整的 Web 应用（FastAPI + React 18 + PostgreSQL + Redis + MinIO） |
| 定位 | 单机、本地、模型驱动的"AI 文档→可编辑 PPT"工具 | 多租户、可协作的"AI PPT 平台 + 知识库 + 代理进化" |
| 代码量级 | ~870 commits，单仓多 skill，无后端服务 | 后端 FastAPI + Alembic 8 次迁移 + 前端 React 18 + Vite，模块化分层 |
| 部署 | `pip install -r requirements.txt` 即用 | `make dev` 起 Docker Compose（Postgres/pgvector、Redis、MinIO、Jaeger、Prometheus、Grafana） |
| 计费/版权 | MIT 开源，工具免费，仅付模型 API | 闭源专有，平台自行核算 token |
| 数据归属 | 文件全程本地，仅与模型 API 通信 | 文件存 MinIO，向量存 Postgres pgvector，凭据/事件入业务库 |

---

## 2. PPT-master 的核心能力

### 2.1 差异化的"看家本领"
1. **真·可编辑 PPTX** — AI 先生成 SVG，再用脚本无损转为 DrawingML 原生对象（形状、文本框、渐变、阴影、图表），用户可在 PowerPoint 中逐元素点击修改。
2. **本地优先 / 数据不出端** — 除模型 API 通信外，整套流水线在用户本机跑。
3. **无平台锁定** — 一套 Skill 同时兼容 Claude / GPT / Gemini / Kimi / MiniMax 等多种模型 + 多种 IDE。
4. **多格式输入** — PDF、DOCX、HTML、EPUB、IPynb、Markdown、URL、长文粘贴均可。
5. **可选自家模板** — 可注入用户 `.pptx` 模板，让生成结果继承公司 VI（字体/色/页脚/Logo）。
6. **原生动画与转场** — DrawingML 层级的入场动画 + 幻灯片切换，而非嵌入视频。
7. **演讲者备注 & 语音旁白** — 自动生成备注，可合成音频旁白，支持**声音克隆**。
8. **多模态配图** — `gpt-image-2` AI 生图 + Pexels / Pixabay 联网搜图，落地到幻灯片。
9. **多种预设视觉风格** — Editorial、Data-Journalism、Swiss Grid、Glassmorphism、Memphis、Risograph Zine、Blueprint、Brutalist、Chalkboard、Dark-tech、Ink-notes、Ink-wash、Paper-cut、Photo-editorial、Pixel-art、Sketch-notes、Soft-rounded、Vintage-poster、Zine 等十余套。
10. **多沟通模式 (Communication Mode)** — briefing、instructional、narrative、pyramid、showcase，约束信息组织节奏。
11. **多画幅输出** — 16:9、4:3、小红书 3:4、朋友圈 1:1、Story 9:16、A4 等。
12. **可插拔的"Skill 市场"** — 通过 `npx skills add hugohe3/ppt-master` 一键安装到 Claude Code / Cursor / Codex。

### 2.2 短板（项目方也公开承认）
- 配置门槛：需装 Python、装 IDE、装依赖，首次 ~15min。
- 速度慢：逐页串行生成，10 页需 10–20min（SaaS 几秒但质量不可比）。
- 没有可视化拖拽画布：所有操作靠对话。
- 图表是"视觉形状"：可看不可点进数据编辑（与本项目"原生 DrawingML 图表"目标略有差距）。
- 极强依赖模型：作者明确写"harness + model = agent"，建议 Claude Opus 4.7 + gpt-image-2 才能拉满。
- 无团队协作 / 权限 / 审计：单用户单端，无知识沉淀。

---

## 3. PPT_Agent 已交付能力（M0–M5）

### 3.1 平台与基础设施
- **多租户体系**：User / API Key / 凭据（Credential）/ 偏好 / 安全事件；Dev Key 自注入。
- **完整基础设施**：Postgres 16 + pgvector、Redis 7、MinIO、Jaeger、Prometheus、Grafana。
- **可观测性**：OpenTelemetry 接入，Trace 中间件逐 stage 记录，WS 实时推送进度。
- **数据生命周期**：导出 / 删除用户全量数据（GDPR/合规）。
- **可插拔调度**：Redis 队列 + Worker，幂等中间件防重放。

### 3.2 知识库与素材
- **样例管理**：上传 PPTX 样本 → 解析 → 嵌入 → 入库；支持去重、PII 检测。
- **素材库 (Material)**：导入/分类/检索，含 `material_search` 服务 + 性能测试。
- **偏好学习**：自动从历史任务中抽取 Style Preferences。
- **来源溯源 (Source Attribution)**：生成内容可回溯到原始素材 chunk。

### 3.3 生成流水线
- **4 阶段管线**：outline → points → svg → pptx，每阶段独立 trace，可重跑。
- **两种模式**：
  - **Reference 模式**：基于样例的风格对齐（font/layout/palette 三维评分）。
  - **General 模式**：纯 LLM 驱动，可加载 Communication Mode + Visual Style。
- **风格适配**：5 种沟通模式 + 17+ 视觉风格预设（与 PPT-master 在 spec 层同构）。
- **原生 DrawingML 渲染**：`backend/src/integrations/ppt_engine/scripts/pptx_renderer/` 提供 SVG → DrawingML 全套转换，与 PPT-master 同思路。
- **样式评分**：`LayoutScorer / PaletteScorer / FontScorer` 量化生成质量。
- **ReDo / Trace**：失败 stage 可定点重跑，不重头再来。

### 3.4 协作与编辑
- **草稿 (Draft)**：list / detail / 锁定 / 解锁 / 导出 `.pptx`；WebSocket 订阅锁变更。
- **REST + WS API**：统一 OpenAPI 契约，生成过程实时事件流。
- **PII 检测**：上传与生成阶段双重检测 + UI 标记。
- **Pact 契约测试 + e2e**：US1–US5 全部 Playwright 覆盖。

### 3.5 代理与扩展
- **AgentScope 集成**：`agentscope_compat` 适配层，ReAct Agent + Orchestrator。
- **中间件链**：Behavior / PII / Trace 三类中间件，可热插拔。
- **可扩展工具集**：Knowledge Retriever / PII Detector / Style Normalizer / Sample Parser / PPTX Renderer。

---

## 4. 维度化差异对比

### 4.1 形态与分发

| 子项 | PPT-master | PPT_Agent | 差距分析 |
| --- | --- | --- | --- |
| 分发方式 | Skill 包，IDE 内对话 | 独立 Web 应用 | PPT-master 易获客，本项目"重" |
| 部署成本 | 一行 pip | Docker Compose + DB/缓存/对象存储 | 本项目运维成本高 |
| 使用门槛 | 需要懂 AI IDE + 写好 prompt | 浏览器点点即可 | **本项目更易上手** |
| 并发协作 | ❌ 单机单人 | ✅ 多用户、API Key、租户隔离 | **本项目优势** |
| 模型选择 | 任意模型，随用户 | 用户自带 Credential（已抽象 LLMClient） | 双方均灵活 |

### 4.2 输入与素材

| 子项 | PPT-master | PPT_Agent | 差距分析 |
| --- | --- | --- | --- |
| 文档输入 | PDF/DOCX/HTML/EPUB/IPynb/MD/URL | 样例 PPTX、源文档 chunk、Material 库 | **PPT-master 格式更广** |
| 自家模板支持 | ✅ 任意 .pptx 模板 | ❌ 当前为预置样式 | **PPT-master 强项** |
| 知识沉淀 | ❌ 无，文档用一次丢一次 | ✅ 嵌入 + 向量检索 + 偏好学习 | **本项目护城河** |
| 样例驱动 | ❌ | ✅ 上传→解析→评分→风格对齐 | **本项目护城河** |

### 4.3 生成能力

| 子项 | PPT-master | PPT_Agent | 差距分析 |
| --- | --- | --- | --- |
| 视觉风格 | 17+ 预设，由 LLM 在风格 spec 下自由生成 | 17+ 预设（同一 spec 体系），受 Reference / General 模式驱动 | 风格库同源；本项目可与样例混搭 |
| 沟通模式 | 5 种（briefing/instructional/narrative/pyramid/showcase） | 5 种（同一 spec） | 同源对齐 |
| 多画幅 | 16:9 / 4:3 / 3:4 / 1:1 / 9:16 / A4 | 当前主要为 16:9（viewBox 1280×720） | **PPT-master 领先** |
| 真·可编辑 DrawingML | ✅ | ✅（同 `pptx_renderer` 体系） | 双方同能力 |
| 动画 & 转场 | ✅ 原生 | ⚠️ 框架已留 `animation_config` 入口，未启用 | **PPT-master 领先** |
| 演讲者备注 & 旁白 | ✅ 含 TTS、声音克隆 | ⚠️ 备注生成已有（T040 `points.notes`），未做 TTS | **PPT-master 领先** |
| AI 配图 | ✅ gpt-image-2 + Pexels/Pixabay | ⚠️ 素材库已有，但未在生成阶段自动选图 | **PPT-master 领先** |
| 图表 | "视觉形状"假图 | 已抽象为 LLM 生成 SVG → DrawingML | 本项目略胜（更"原生"） |
| 评分体系 | ❌ | ✅ layout/palette/font + overall | **本项目独有** |
| 阶段级重做 | ❌ 整篇重跑 | ✅ Trace + ReDo 单 stage | **本项目独有** |

### 4.4 协作 / 合规 / 可观测

| 子项 | PPT-master | PPT_Agent | 差距分析 |
| --- | --- | --- | --- |
| 多用户 / 权限 | ❌ | ✅ | **本项目优势** |
| 审计 / 安全事件 | ❌ | ✅ security_events 表 | **本项目优势** |
| PII 检测 | ❌ | ✅ 上传 + 生成双检 | **本项目优势** |
| 数据生命周期 | ❌ | ✅ 导出 / 一键删除 | **本项目优势** |
| 实时进度 | 仅 IDE 日志 | ✅ WebSocket 推送 + UI 队列指示 | **本项目优势** |
| 可观测性 | ❌ | ✅ Jaeger + Prometheus + Grafana | **本项目优势** |

### 4.5 架构与扩展性

| 子项 | PPT-master | PPT_Agent | 差距分析 |
| --- | --- | --- | --- |
| 编排 | AI 自由对话 + 内置 Skill 流程 | 显式 4 阶段 + Middleware + Orchestrator | 本项目更工程化 |
| Agent 框架 | 依赖宿主 AI | 集成 AgentScope + ReAct + 自定义工具 | **本项目优势** |
| 后端服务 | 无 | FastAPI + SQLAlchemy + Alembic | **本项目优势** |
| 前端 | 无 | React 18 + Vite + Tailwind + Radix | **本项目优势** |
| 扩展机制 | 替换 / 新增 Skill | 模块化 services/tools/middleware | 双方皆可 |

---

## 5. 本项目相对 PPT-master 的护城河

1. **多租户 + 权限 + 审计** — 适合企业落地。
2. **样例驱动的"风格对齐"生成** — 独家能力，远比"套预设风格"更接近"做我司的 PPT"。
3. **知识库 + 向量检索 + 来源溯源** — 让"素材—生成—证据"形成闭环。
4. **阶段级 Trace + ReDo** — 长链路任务的工业化能力。
5. **样式三维评分** — 量化质量，可观测、可回归。
6. **完整可观测性栈** — Jaeger / Prometheus / Grafana 接 OTEL。
7. **数据生命周期** — 合规就绪。
8. **PII 中间件 + 安全事件** — 涉外业务刚需。

---

## 6. 借鉴 PPT-master 的可落地项（Roadmap 输入）

按"用户价值 × 实施成本"排序，建议优先级：

| P | 能力 | 价值 | 落地建议 |
| --- | --- | --- | --- |
| **P0** | **动画 & 转场** | 高 | 复用现有 `animation_config.py`，在 `pptx_renderer` 中默认开启淡入/擦除，飞入作为可选；UX 上做"是否启用动画"开关 |
| **P0** | **演讲者备注 → 旁白 TTS** | 高 | 备注已在 `points.notes`；接入 TTS 服务（DashScope / OpenAI / Edge），输出 MP3 嵌入 PPTX 备注页 |
| **P1** | **多画幅输出** | 中 | 后端抽象 `CanvasSpec`（16:9 / 4:3 / 3:4 / 9:16 / A4），在 `pipeline._stage_svg_general` 视口处切换，DB 落 `canvas_spec` 字段 |
| **P1** | **AI 配图（gpt-image / Pexels / Pixabay）** | 中 | 在 SVG stage 之后、PPTX stage 之前插入 `image_resolver` 工具；优先复用 Material 库，回退到外部 API |
| **P1** | **支持自家 .pptx 模板** | 中-高 | 引入"模板抽取器"：从上传模板解析主色 / 字体 / 母版版式，存为 visual style spec，可被 generation 复用 |
| **P2** | **更多文档输入格式** | 中 | 接入 Unstructured / MarkItDown，统一转 MD 后走现有 chunk → embed 链路 |
| **P2** | **声音克隆 / 品牌声音** | 中 | 旁白服务的扩展项，依赖 TTS 提供方能力 |
| **P2** | **Skill 化打包** | 战略 | 把本项目打包为 Claude Code / Cursor / Trae 可加载的 Skill，把 Web 平台的生成能力"反向"导流到 IDE 用户；与 PPT-master 在分发侧同台 |

---

## 7. 总结

- **PPT-master = 个人极客的最强"本地 PPT 工坊"**：极致可编辑、风格丰富、模型无关、零运维，但缺协作、合规、知识沉淀。
- **PPT_Agent = 企业的"AI PPT 平台"**：多租户 / 合规 / 知识库 / 样例驱动 / 工业级可观测，但风格广度（动画、旁白、配图、多画幅、模板）尚需补齐。
- **竞争策略**：护城河在"知识库 + 样例风格对齐 + 协作合规"；补齐方向在"动画 / 旁白 / 配图 / 多画幅 / 模板"。
- **差异化护城河**（不可被 PPT-master 短期复制）：样例驱动的"我司 PPT 风格"、阶段级 Trace + ReDo、三维样式评分、企业级权限与审计。
