# API Interface Design: PPTagent MVP

**Branch**: `001-mvp-closed-loop` | **Date**: 2026-06-24
**配套契约**: [openapi.yaml](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/contracts/openapi.yaml) · [events.yaml](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/contracts/events.yaml) · [error-codes.yaml](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/contracts/error-codes.yaml)
**对应阶段**: 全部 5 个 User Story（US1–US5）

> 本文是 PPTagent MVP 对外接口的**设计规范**，回答"为什么这么设计 / 怎么用 / 如何演进"。
> 三份 YAML 是机器可读的**契约真值**；本文是面向开发者的**设计意图说明**。

---

## 1. 设计原则

| # | 原则 | 落地 |
|---|------|------|
| **API-1** | **REST + WebSocket 混合** | 同步 CRUD 用 REST，实时进度/队列/轨迹用 WS |
| **API-2** | **API Key 最小权限** | `Authorization: Bearer <key>` 唯一鉴权方式；scope 数组限制能力 |
| **API-3** | **异步优先** | 长任务（生成/解析/导出/删除）一律 `202 Accepted` + 任务 ID |
| **API-4** | **可幂等** | 写入类 POST MUST 支持 `Idempotency-Key` 头去重 |
| **API-5** | **可追溯** | 所有响应携带 `X-Request-Id`，与 trace 系统打通 |
| **API-6** | **错误标准化** | 严格遵循 RFC 7807（`application/problem+json`） |
| **API-7** | **版本前置路径** | `/api/v{major}` 形式；不引入 header 版本 |
| **API-8** | **生成轨迹优先** | 所有 AI 行为 MUST 可通过 `/trace` + `/stages/{name}/redo` 拉取与回退 |
| **API-9** | **数据安全前置** | 任何返回原始文件/PII 的端点 MUST 走 scope 检查 |
| **API-10** | **OpenAPI 单一真值** | `openapi.yaml` 是契约源；DTO 改动 MUST 先改 YAML 再生成 |

---

## 2. 版本与基址

```
{scheme}://{host}/api/v{major}/{resource}
```

| 环境 | Base URL | 说明 |
|------|----------|------|
| 本地开发 | `http://localhost:8000/api/v1` | Vite + Uvicorn |
| 预发 | `https://staging-api.pptagent.example.com/api/v1` | 内部 |
| 生产 | `https://api.pptagent.example.com/api/v1` | 私有化 Beta |

**版本规则**（Constitution §VII）：
- **MAJOR**（v1 → v2）：破坏性变更（移除端点、改字段类型、错误码重组）
- **MINOR**（v1.0 → v1.1）：新增端点/字段
- **PATCH**（v1.0.0 → v1.0.1）：文档/示例修正

**兼容性承诺**：
- v1 内不允许删除端点；如需弃用走 `/api/v2` + 旧版本 deprecation 头
- 新增字段在响应中向后兼容（旧客户端不读新字段即忽略）

---

## 3. 通用 Headers

### 3.1 请求头

| Header | 必需 | 格式 | 说明 |
|--------|------|------|------|
| `Authorization` | ✅ | `Bearer sk-xxxxxxxx` | API Key 鉴权 |
| `Content-Type` | POST/PUT 时 | `application/json` 或 `multipart/form-data` | |
| `Idempotency-Key` | POST 推荐 | UUIDv4 | 24h 内同 key 同请求体去重；防止重复点击 |
| `X-Request-Id` | 推荐 | UUIDv4 | 客户端生成；服务端透传到 trace |
| `Accept-Language` | 否 | `zh-CN` / `en-US` | 错误信息本地化（v1 仅 zh-CN） |

### 3.2 响应头

| Header | 出现时机 | 说明 |
|--------|----------|------|
| `X-Request-Id` | 全部 | 与入参一致或服务端生成；用于日志关联 |
| `X-RateLimit-Limit` | 全部 | 当前 key 的速率上限（次/分） |
| `X-RateLimit-Remaining` | 全部 | 当前窗口剩余次数 |
| `X-RateLimit-Reset` | 全部 | Unix 时间戳，窗口重置时刻 |
| `Retry-After` | 429 / 503 | 退避秒数 |
| `Deprecation` | v1 弃用端点 | `true` + `Sunset` 日期 |
| `Link` | 分页响应 | 上一页/下一页 URL（HAL 风格） |
| `Content-Type` | 全部 | `application/json` 或 `application/problem+json` |

### 3.3 速率限制（FR-029 部分）

| Scope | 默认阈值 | 超出行为 |
|-------|----------|----------|
| `generation:write` | 60 req/min | 429 + `Retry-After: 30` |
| `sample:write` | 30 req/min | 429 |
| `read:*` | 600 req/min | 429 |
| `export:write` | 5 req/day | 429 |
| `delete-all:write` | 1 req/day | 429 + 强制二次确认 |

> 阈值在 `api_keys.rate_limit_per_min` 覆盖；企业 tier 可上调。

---

## 4. 鉴权与最小权限

### 4.1 三类 Scope

```
generation:write   创建/取消生成任务
generation:read    查询任务状态与轨迹
sample:write       上传/删除样本
sample:read        列出/下载样本摘要
preference:read    读取偏好规则
preference:write   删除偏好规则
data:export        导出个人数据
data:delete-all    一键删除（最敏感；强制二次确认）
security:read      读取安全事件
```

### 4.2 鉴权流程

```
┌────────┐                              ┌────────┐
│ Client │                              │ Server │
└───┬────┘                              └───┬────┘
    │  1. POST /generations                 │
    │     Authorization: Bearer sk-abc1...  │
    │     Idempotency-Key: <uuid>           │
    │──────────────────────────────────────>│
    │                                       │
    │                          2. SHA-256(key) → api_keys.key_hash
    │                          3. Check revoked_at IS NULL
    │                          4. Check scopes ∋ 'generation:write'
    │                          5. Check rate_limit
    │                          6. SET LOCAL app.user_id = owner_id
    │                                       │
    │  7. 202 Accepted                      │
    │     X-Request-Id: <uuid>              │
    │     X-RateLimit-Remaining: 59         │
    │     Location: /api/v1/generations/{id}│
    │<──────────────────────────────────────│
```

### 4.3 二次确认（data:delete-all）

```http
POST /api/v1/data/delete-all
Authorization: Bearer sk-...
Content-Type: application/json

{ "confirm_phrase": "DELETE ALL MY DATA", "acknowledged_at": "2026-06-24T10:00:00Z" }
```

服务端 MUST 校验 `confirm_phrase` 字面量匹配，**不匹配 → 400 PPTAGENT.CONFIRM_REQUIRED**。

---

## 5. 异步任务模式

### 5.1 三种任务模型

| 模型 | 适用场景 | 同步 vs 异步 | 状态查询 |
|------|----------|--------------|----------|
| **即时** | 列出/查询/取消 | 同步 200/204 | 一次性响应 |
| **短任务** | 偏好删除、安全事件查询 | 同步 200/204 | 一次性响应 |
| **长任务** | 生成/解析/导出/批量删除 | 异步 202 + task_id | WS 订阅 + GET 兜底 |

### 5.2 长任务统一规范

```http
POST /api/v1/generations
→ 202 Accepted
{
  "id": "uuid",
  "status": "queued",
  "queue_position": 3,
  ...
}

GET /api/v1/generations/{id}
→ 200 OK
{
  "id": "uuid",
  "status": "success" | "failed" | "cancelled" | "archived",
  "result_pptx_url": "...",
  "style_fit_score": { "layout": 0.85, "palette": 0.92, "font": 0.88, "is_fit": true }
}
```

### 5.3 实时进度（WebSocket）

详见 [events.yaml](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/contracts/events.yaml) 与 [§8 WebSocket 协议](#8-websocket-协议)。

---

## 6. 分页与列表约定

### 6.1 列表端点统一规范

```http
GET /api/v1/samples?page=1&page_size=20&sort=-uploaded_at&file_type=pptx&parse_status=parsed
→ 200 OK
{
  "items": [...],
  "page": 1,
  "page_size": 20,
  "total": 137,
  "has_next": true,
  "next": "/api/v1/samples?page=2&page_size=20",
  "prev": null
}
```

### 6.2 查询参数约定

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `page` | int ≥ 1 | 1 | 页码（从 1 起） |
| `page_size` | int 1–100 | 20 | 每页条数 |
| `sort` | string | `-created_at` | `-` 前缀 DESC；支持 `-uploaded_at`、`last_applied_at` 等 |
| `cursor` | string | – | **大表分页**（`security_events` 月度分区表超过 10k 条时） |

### 6.3 何时用 cursor

| 端点 | 列表量级 | 分页方式 |
|------|----------|----------|
| `/generations` | 单用户 1000s | page |
| `/samples` | 单用户 100s | page |
| `/preferences` | 单用户 10s | page |
| `/security/events` | 单用户 100k+ | **cursor**（按 created_at 微秒精度游标） |

---

## 7. 错误响应（RFC 7807）

### 7.1 完整 Problem JSON 结构

```json
{
  "type": "https://docs.pptagent.example.com/errors/PPTAGENT.KB_EMPTY",
  "title": "知识库为空",
  "status": 422,
  "detail": "用户尚未上传任何样本，无法生成",
  "code": "PPTAGENT.KB_EMPTY",
  "instance": "/api/v1/generations",
  "request_id": "01J6H8X9K0...",
  "trace_id": "abc123...",
  "errors": [
    { "field": "prompt", "message": "must not be empty", "code": "too_short" }
  ]
}
```

完整错误码清单见 [error-codes.yaml](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/contracts/error-codes.yaml)。

### 7.2 重试策略

| HTTP | 含义 | 客户端行为 |
|------|------|------------|
| **400 / 422** | 客户端错误 | 不重试；提示用户 |
| **401** | 未认证 | 刷新 token 后重试 |
| **403** | scope 不足 | 不重试；申请更高权限 |
| **404** | 资源不存在 | 不重试 |
| **409** | 状态冲突 | 刷新资源状态后判断 |
| **429** | 速率/并发 | 按 `Retry-After` 退避 |
| **500** | 服务端 | 指数退避 3 次 |
| **502 / 503** | 上游不可用 | 退避后重试；写入 trace |
| **504** | 超时 | 同 502 |

---

## 8. WebSocket 协议

### 8.1 端点

```
wss://api.pptagent.example.com/api/v1/ws
```

握手：复用 REST 鉴权（`Authorization: Bearer ...` 头）。

### 8.2 订阅模型

```json
// Client → Server
{
  "action": "subscribe",
  "channel": "task:01HXYZ...",
  "request_id": "01J6H8..."
}

// Server → Client
{
  "type": "ack",
  "channel": "task:01HXYZ...",
  "request_id": "01J6H8..."
}
```

**可订阅频道**:

| 频道 | 推送事件 | 鉴权 |
|------|----------|------|
| `task:{task_id}` | `task.stage.started` / `task.stage.finished` / `task.finished` | 仅任务所有者 |
| `user:{user_id}:queue` | `queue.position_changed` | 仅本人 |
| `user:{user_id}:security` | `security.event_created` | 仅本人 |

### 8.3 心跳与重连

- **心跳**：30s 一次双向 PING/PONG
- **断线重连**：客户端 MUST 携带 `Last-Event-ID` 重连，服务端从该 ID 之后的事件开始重放（最多 1000 条）
- **背压**：服务端单连接最多缓冲 1000 条事件；超出后强制关闭（客户端应实现重连）

### 8.4 事件定义

见 [events.yaml](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/contracts/events.yaml) 完整定义。

---

## 9. 幂等性（Idempotency-Key）

### 9.1 适用范围

所有写入类 POST MUST 支持：

- `POST /generations`
- `POST /generations/{id}/stages/{name}/redo`
- `POST /samples/batch`
- `POST /data/export`
- `POST /data/delete-all`

### 9.2 行为

```http
POST /api/v1/generations
Idempotency-Key: 7c4e8a3f-...
Body: { "prompt": "..." }
→ 202 Accepted { "id": "task-1" }

# 24h 内同 key 同 body：
POST /api/v1/generations
Idempotency-Key: 7c4e8a3f-...
Body: { "prompt": "..." }
→ 202 Accepted { "id": "task-1" }   ← 返回首次结果
```

- 同 key 不同 body → **422 PPTAGENT.IDEMPOTENCY_MISMATCH**
- 同 key 同 body → 返回首次响应 + `Idempotency-Replay: true` 头

### 9.3 存储

`idempotency_keys` 表：

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | UUIDv4 | PK |
| `owner_id` | UUID | 多租户隔离 |
| `method` | string | HTTP method |
| `path` | string | 规范化 |
| `request_hash` | SHA-256(body) | body 去重 |
| `response_status` | int | 首次响应 |
| `response_body` | JSONB | 首次响应 |
| `created_at` | TIMESTAMPTZ | 24h 后清理 |

---

## 10. CORS 与安全

### 10.1 CORS

```
Access-Control-Allow-Origin:   https://app.pptagent.example.com  (生产) / http://localhost:5173 (开发)
Access-Control-Allow-Methods:  GET, POST, DELETE, OPTIONS
Access-Control-Allow-Headers:  Authorization, Content-Type, Idempotency-Key, X-Request-Id
Access-Control-Expose-Headers: X-Request-Id, X-RateLimit-*
Access-Control-Max-Age:        600
```

### 10.2 安全

- **HTTPS Only**（生产）— `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- **API Key 永不返回明文**（仅 `key_prefix` + 创建时一次性明文）
- **PII 字段响应脱敏**（手机 `138****5678`、身份证 `110101****1234`、邮箱 `a***@example.com`）
- **审计日志**：所有写操作 MUST 写 `security_events` 或对应 trace

---

## 11. SDK 与文档生成

### 11.1 TypeScript 客户端

```bash
# frontend/package.json
pnpm gen:api   # = openapi-typescript ../specs/001-mvp-closed-loop/contracts/openapi.yaml -o src/services/api.d.ts
```

**使用示例**:

```typescript
import { createGeneration, getGeneration } from '@/services/api';

const { task_id } = await createGeneration({ prompt: '...' });
const task = await getGeneration({ path: { task_id } });
```

### 11.2 Python 客户端

```bash
# 自动生成
openapi-python-client generate --path contracts/openapi.yaml --output-path backend/src/clients/pptagent_sdk
```

### 11.3 Mock 服务器

```bash
# 本地开发无需真实后端时
docker run -p 4010:4010 \
  -v $PWD/specs/001-mvp-closed-loop/contracts/openapi.yaml:/tmp/openapi.yaml \
  stoplight/prism:5 mock -d /tmp/openapi.yaml --port 4010
```

前端 `VITE_API_BASE_URL=http://localhost:4010` 即可对接 mock。

### 11.4 文档站

```bash
redoc-cli bundle specs/001-mvp-closed-loop/contracts/openapi.yaml -o docs/api.html
# 或部署到 GitHub Pages
```

---

## 12. 端点总览

> 完整定义见 [openapi.yaml](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/contracts/openapi.yaml)。

| 方法 | 路径 | Scope | 阶段 | 说明 |
|------|------|-------|------|------|
| POST | `/generations` | `generation:write` | US1 | 一句话生成 |
| GET | `/generations/{id}` | `generation:read` | US1 | 查询状态 |
| DELETE | `/generations/{id}` | `generation:write` | US1 | 取消 |
| GET | `/generations/{id}/trace` | `generation:read` | US4 | 轨迹 |
| POST | `/generations/{id}/stages/{name}/redo` | `generation:write` | US4 | 阶段重做 |
| GET | `/samples` | `sample:read` | US2 | 列表 |
| POST | `/samples/batch` | `sample:write` | US2 | 批量上传 |
| GET | `/samples/{id}` | `sample:read` | US2 | 样本详情（PII 摘要 + 解析结果） |
| DELETE | `/samples/{id}` | `sample:write` | US2 | 删除样本 |
| POST | `/samples/{id}/reparse` | `sample:write` | US2 | 强制重新解析 |
| GET | `/preferences` | `preference:read` | US3 | 列表 |
| GET | `/preferences/{id}` | `preference:read` | US3 | 详情（含来源链） |
| DELETE | `/preferences/{id}` | `preference:write` | US3 | 删除偏好 |
| POST | `/data/export` | `data:export` | US5 | 申请打包 |
| GET | `/data/export/{job_id}` | `data:export` | US5 | 导出进度 / 下载链接 |
| POST | `/data/delete-all` | `data:delete-all` | US5 | 一键删除（带二次确认） |
| GET | `/security/events` | `security:read` | US5 | 安全事件流（cursor 分页） |
| POST | `/api_keys` | `api_key:write` | INFRA | 签发新 key（明文仅返一次） |
| GET | `/api_keys` | `api_key:read` | INFRA | 列出 key |
| DELETE | `/api_keys/{id}` | `api_key:write` | INFRA | 撤销 key |
| GET | `/healthz` | – | INFRA | 健康检查（无鉴权） |
| GET | `/metrics` | – | INFRA | Prometheus（无鉴权） |
| WS | `/ws` | 任意 | US1/US2/US3/US4 | 实时事件（握手鉴权） |
| GET | `/materials` | `material:read` | **US6** | 素材库检索（BM25 + 嵌入向量双路召回） |
| GET | `/materials/{id}` | `material:read` | **US6** | 素材详情（含 SVG 原文 / 风格指纹） |
| DELETE | `/materials/{id}` | `material:write` | **US6** | 删除素材（不级联 sample） |
| POST | `/materials/{id}/insert` | `material:write` | **US6** | 将素材插入草稿（FR-033 + FR-034 风格归一开关） |
| GET | `/drafts` | `draft:read` | **US6** | 列出草稿 |
| POST | `/drafts` | `draft:write` | **US6** | 创建草稿 |
| GET | `/drafts/{id}` | `draft:read` | **US6** | 草稿详情（含 slides 列表） |
| PATCH | `/drafts/{id}` | `draft:write` | **US6** | 更新草稿（乐观锁 expected_revision） |
| DELETE | `/drafts/{id}` | `draft:write` | **US6** | 归档草稿 |
| POST | `/drafts/{id}/lock` | `draft:write` | **US6** | 获取编辑锁（30 分钟自动过期） |
| DELETE | `/drafts/{id}/lock` | `draft:write` | **US6** | 释放编辑锁 |
| PATCH | `/drafts/{id}/slides/{sid}` | `draft:write` | **US6** | 调整草稿单张页（顺序 / 样式 / 文本） |
| DELETE | `/drafts/{id}/slides/{sid}` | `draft:write` | **US6** | 删除草稿中的某张页 |
| POST | `/drafts/{id}/export` | `draft:write` | **US6** | 导出草稿为 PPTX（FR-036 保留来源标注） |
| GET | `/drafts/{id}/export/{job_id}` | `draft:read` | **US6** | 查询导出任务进度 |

---

## 13. 演进策略

| 阶段 | 端点增量 | 关注点 |
|------|----------|--------|
| **v0.1 (M1)** | 11 个端点 | MVP 闭环；FR-001–FR-005 |
| **v0.2 (M2)** | + 3 个 | FR-006/007/008/010 |
| **v0.3 (M3)** | + 2 个 | FR-011–FR-017 |
| **v1.0 (M4)** | + 4 个 | FR-018–FR-028 + API Key 管理 |
| **v2.0 (GA)** | + 团队协作端点 | 多用户协作、模板市场 |

---

## 14. 与 Constitution 的映射

| Constitution 条款 | 落地位置 |
|--------------------|----------|
| §I 二开优先 | API 层在 `AgentScope 2.0` 之上；不引入新框架 |
| §II MVP 驱动 | v0.1 仅含 US1 端点即可演示 |
| §III 可解释可控制 | `/trace` + `/stages/{name}/redo` 必为 v0.1 一部分 |
| §IV 数据安全 | `data:export` / `data:delete-all` 必须二次确认；PII 字段响应脱敏 |
| §V 可观测 | `X-Request-Id` + trace middleware 串联 |
| §VI 测试门禁 | 合同测试 (Pact) MUST 在 PR 前绿；CI 第 3 阶段 |
| §VII 语义化版本 | `/api/v{major}` 路径版本；`info.version` 字段同步 |
| **§II 资产复用（M5 US6）** | 素材库（`/materials`）= 个人知识库 RAG 的衍生；不引入第二套向量索引 |
| **§IV 样本解耦（US6）** | `DELETE /samples/{id}` MUST 不级联 `slide_assets`；素材变孤儿但保留可检索 |
| **§V 行为可追溯（US6）** | 草稿导出 PPTX 写入 XMP / 自定义 XML 来源标注，便于审计 |

---

**Interface Design Status**: ✅ 设计规范完成
**Recommended Next**: 在 `/speckit.implement` 阶段将 §3/§4 headers 落地为 FastAPI 中间件（T017、T020），§5 异步模式落地为 worker 与 WS 服务（T042、T046），§9 幂等表新增为 T016a。

---

## 15. 实施落地映射

> 本节将接口设计的每个组件映射到 [tasks.md](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/tasks.md) 中的具体实现任务，便于实施阶段逐项落地。

| 设计组件 | 落地任务 | 文件路径 |
|----------|----------|----------|
| §3 `X-Request-Id` 请求头 | **T017** [CORE] | `backend/src/middleware/request_id.py` |
| §4 鉴权（API Key + scope 校验） | **T020** [CORE] | `backend/src/middleware/auth.py` |
| §4 速率限制 | **T021** [CORE] | `backend/src/middleware/rate_limit.py`（Redis token bucket） |
| §5 异步任务 `202 Accepted` | **T042** [CORE] | `backend/src/scheduler/worker.py` |
| §5 排队位置 `queue_position` | **T043** [CORE] | `backend/src/api/generations.py` |
| §6 cursor 分页 | **T053** [P] | `backend/src/api/pagination.py` |
| §7 RFC 7807 错误响应 | **T022** [CORE] | `backend/src/middleware/problem.py` |
| §8 WebSocket `/ws` | **T046** [CORE] | `backend/src/api/ws.py` |
| §9 `Idempotency-Key` | **T016a** [CORE] | 新增 idempotency_keys 表 + 迁移 `0003_idempotency.py` + 中间件 `backend/src/middleware/idempotency.py` |
| §10 CORS | **T018** [CORE] | `backend/src/main.py`（FastAPI CORSMiddleware） |
| §11 OpenAPI 单一真值 | **T015** [CORE] | `contracts/openapi.yaml`（CI 校验） |
| §12 端点实现 | **T043–T052**, **T060–T067** | 各 `backend/src/api/*.py` |
| §13 版本路径 `/api/v{major}` | **T019** [CORE] | `backend/src/main.py`（路由前缀） |
| §13 `info.version` 同步 | **T015** [QA] | CI 校验 openapi.yaml 与 pyproject.toml 版本一致 |

### 15.1 T016a 幂等表 DDL（新增迁移）

```sql
-- backend/src/db/migrations/versions/0003_idempotency.py
CREATE TABLE idempotency_keys (
    key            UUID         PRIMARY KEY,           -- = Idempotency-Key header
    owner_id       UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    request_hash   CHAR(64)     NOT NULL,              -- SHA-256(body)
    response_status SMALLINT    NOT NULL,
    response_body  JSONB        NOT NULL,
    task_id        UUID,                                -- 若创建了异步任务
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    expires_at     TIMESTAMPTZ  NOT NULL DEFAULT now() + interval '24 hours',

    CONSTRAINT idempotency_keys_hash_chk CHECK (char_length(request_hash) = 64)
);

CREATE INDEX idx_idempotency_keys_owner_expiry
    ON idempotency_keys (owner_id, expires_at);
```

**中间件行为**：
1. 看到 `Idempotency-Key` 头 → 计算 `request_hash = SHA-256(body)`；
2. `INSERT ... ON CONFLICT`：
   - 无冲突：执行业务，写入响应；
   - `request_hash` 匹配：直接返回 200/202 + `Idempotency-Replay: true`；
   - `request_hash` 不匹配：返回 **422 PPTAGENT.IDEMPOTENCY_MISMATCH**。
3. 24h 后由 cron 清理（FR-026 数据保留）。

### 15.2 WS 鉴权与子协议（§8 落地）

| 维度 | 选型 | 理由 |
|------|------|------|
| 鉴权 | 握手时 `Authorization: Bearer <key>` 头 | 与 REST 一致；scope 检查同 §4 |
| 子协议 | `graphql-ws`（订阅风格） | 与前端 React 生态 `graphql-ws` 客户端天然兼容 |
| 心跳 | 服务端 30s ping / 客户端 MUST 30s 内 pong | FR-025 SLA 5% 留余给网络抖动 |
| 重连 | 客户端指数退避（1s → 30s） + `Last-Event-Id` 头补漏 | 避免事件丢失 |
| 鉴权失败 | 1008 Policy Violation 关闭 | 与浏览器原生兼容 |
| 订阅超时 | 5s 内未发送 subscribe → 1008 关闭 | 防空闲长连接耗尽 |

### 15.3 US6 素材检索与方案拼装（设计要点）

> 对应 [spec.md §US6](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/spec.md) 与 [data-model.md §2.2.10~13](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/data-model.md)。本节解释“为什么这样设计”，实施时按 §15.1 同样的 DDL + 任务映射落地。

#### 15.3.1 检索：BM25 × 嵌入向量双路召回（FR-031）

- 召回：`material_search_index.text_tsv`（GIN）+ `slide_assets.embedding`（cosine）同时跑，由 `material_search.py::hybrid_search()` 归一化加权（0.4 / 0.4 / 0.2 视觉类型 boost）。
- 排序：DAL 端用 `ts_rank_cd` 与 `1 - (embedding <=> :vec)`，由应用层按 SC-015 端到端 P95 ≤ 1s 倒推索引策略（IVFFlat lists=100 在 ≥ 1000 行时启用）。
- URL 序列化：所有筛选条件进 query，便于分享/回放（spec FR-032）。

#### 15.3.2 草稿一致性：单写者 + 乐观锁（FR-035）

- **单写者锁**：`POST /drafts/{id}/lock` 写 `editor_user_id` + `editor_lock_at`；其余用户对该草稿的全部写接口返回 423。
- **乐观锁**：所有 `PATCH /drafts/{id}` 与 `PATCH /drafts/{id}/slides/{sid}` MUST 携带 `expected_revision`；服务端 `last_saved_revision` 不匹配 → 409 + Problem details。
- **自动过期**：cron 每 5 分钟 `UPDATE drafts SET editor_user_id=NULL WHERE editor_lock_at < now() - INTERVAL '30 minutes' AND status='active'`。

#### 15.3.3 风格归一：可选 / 失败回退（FR-034）

- 客户端 `enable_style_normalize: true`（默认）→ 服务端调用 `style_normalizer.py::normalize(asset_style, draft_overall_style)`。
- 归一失败（无主色 / 字体冲突 / 版式无法对应）→ `draft_slides.normalized_failed = true` + `style_normalized = false`，并打 `security_events.normalized_failed` 一条审计。
- 归一成功 → `style_normalized = true`，并把 `style_features` 写回 `draft_slides.materialized.style_overrides`。

#### 15.3.4 导出溯源：XMP + 自定义 XML（FR-036）

- 导出 PPTX 时在 `app.xml` 与 `customXml/item1.xml` 写入：
  - `pptagent:draftId` 草稿 UUID
  - `pptagent:slideId` + `pptagent:sourceType` + `pptagent:sourceAttribution`（人类可读）
  - 复用页追加 `pptagent:sourceSampleId` + `pptagent:sourcePageIndex`
- 该 XML 节点不进 PPT 渲染层，但用 `python-pptx` 的 `custom_property_part` 暴露给审计脚本。

#### 15.3.5 错误码新增（与 error-codes.yaml 同步）

| HTTP | code | 触发条件 |
|------|------|----------|
| 409 | `PPTAGENT.MATERIAL_IN_USE` | 删除素材但仍有草稿引用 |
| 409 | `PPTAGENT.DRAFT_REVISION_MISMATCH` | 乐观锁 `expected_revision` 失败 |
| 422 | `PPTAGENT.NORMALIZATION_FAILED` | 风格归一失败（前端可降级为原样） |
| 423 | `PPTAGENT.DRAFT_LOCKED` | 单写者锁被他人持有 |
