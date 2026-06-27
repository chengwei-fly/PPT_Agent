# Data Model: PPTagent MVP 业务闭环

**Branch**: `001-mvp-closed-loop` | **Date**: 2026-06-24
**输入**: [spec.md](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/spec.md) §Key Entities + [plan.md](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/plan.md)

---

## ER 总览

```text
┌─────────────┐ 1   N ┌──────────────┐ 1   N ┌─────────────────┐
│    User     │───────│    Sample    │───────│ ParseResult     │
│             │       │              │       │ (raw_files 表)  │
└─────────────┘       └──────────────┘       └─────────────────┘
       │ 1                                          │ 1
       │                                            │
       │ N                                          │ N
       ▼                                            ▼
┌─────────────────┐ 1   N ┌──────────────────┐ ┌─────────────────┐
│  Preference     │       │ GenerationTask   │ │   Embedding     │
│                 │       │  (tasks 表)      │ │ (embeddings 表) │
└─────────────────┘       └──────────────────┘ └─────────────────┘
                                  │ 1
                                  │
                                  │ N
                                  ▼
                          ┌──────────────────┐
                          │  TraceStage      │
                          │  (trace_stages)  │
                          └──────────────────┘

┌──────────────────┐  N   1 ┌─────────────┐
│ SecurityEvent    │───────│    User     │
│ (security_events)│       │             │
└──────────────────┘       └─────────────┘
```

> 严格遵循 Constitution §IV "原始文件 / 解析结果 / 嵌入向量" 三类分离存储。

---

## 1. User（用户）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | 用户唯一标识 |
| `email` | String(255) | UNIQUE, NOT NULL | 登录邮箱 |
| `display_name` | String(64) | NOT NULL | 显示名 |
| `tier` | Enum(`personal`,`team`,`enterprise`) | NOT NULL, DEFAULT `personal` | 订阅等级 |
| `active_sample_ids` | UUID[] | DEFAULT `[]` | 当前活跃知识库（指向 Sample.id） |
| `api_key_hash` | String(128) | NOT NULL | API Key 哈希（最小权限） |
| `created_at` | TimestampTZ | NOT NULL, DEFAULT now() | 注册时间 |
| `deleted_at` | TimestampTZ | NULL | 软删时间（FR-019 一键删除） |

**索引**: `email`, `tier`, `deleted_at`

### 1a. ApiKey（API Key 多 key 轮换，独立表）

> User.api_key_hash 升级为多 key 模型：支持轮换、撤销、scope 细分。最小权限 (Constitution §IV)。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | |
| `owner_id` | UUID | FK → user.id, NOT NULL | |
| `key_hash` | String(128) | UNIQUE, NOT NULL | SHA-256(key) |
| `key_prefix` | String(8) | NOT NULL | 用于 UI 展示 "sk-abc1..." |
| `scopes` | String[] | NOT NULL, DEFAULT `['generation:write']` | 最小权限 scope 列表 |
| `rate_limit_per_min` | Integer | NOT NULL, DEFAULT 60 | |
| `last_used_at` | TimestampTZ | NULL | |
| `expires_at` | TimestampTZ | NULL | NULL = 永不过期 |
| `revoked_at` | TimestampTZ | NULL | 软撤销 |
| `created_at` | TimestampTZ | NOT NULL, DEFAULT now() | |

**索引**: `key_hash`, `(owner_id, revoked_at)`

---

## 2. Sample（样本）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | 样本唯一标识 |
| `owner_id` | UUID | FK → user.id, NOT NULL | 所有者 |
| `file_name` | String(255) | NOT NULL | 原始文件名 |
| `file_hash` | String(64) | NOT NULL | SHA-256（FR-010 去重） |
| `file_type` | Enum(`pptx`,`pdf`,`docx`) | NOT NULL | 文件类型 |
| `raw_path` | String(512) | NOT NULL | MinIO 原始文件路径（FR-009 三类分离） |
| `parse_status` | Enum(`pending`,`parsing`,`parsed`,`failed`) | NOT NULL, DEFAULT `pending` | 解析状态 |
| `parse_page_count` | Integer | NULL | 解析页数 |
| `pii_summary` | JSONB | NULL | PII 处理摘要（FR-008 字段级处置记录） |
| `uploaded_at` | TimestampTZ | NOT NULL, DEFAULT now() | 上传时间 |
| `parsed_at` | TimestampTZ | NULL | 解析完成时间 |
| `deleted_at` | TimestampTZ | NULL | 软删时间 |

**索引**:
- `UNIQUE(owner_id, file_hash)` — 去重（FR-010）
- `(owner_id, deleted_at)` — 用户维度的活跃样本查询
- `(parse_status)` — 后台解析 worker 查询

**状态机**:
```
pending ──[worker start]──> parsing ──[success]──> parsed
                              │                      │
                              │                      └─[用户删除]──> soft_deleted
                              └──[fail]──> failed ──[用户删除]──> soft_deleted
```

---

## 3. ParseResult（解析结果，独立表）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | |
| `sample_id` | UUID | FK → sample.id, UNIQUE, NOT NULL | 一对一 |
| `structure_json` | JSONB | NOT NULL | 解析后的结构化摘要（页/版式/文本块） |
| `parse_version` | String(16) | NOT NULL | 解析器版本（依赖锁定可追溯） |
| `parse_started_at` | TimestampTZ | NOT NULL | |
| `parse_finished_at` | TimestampTZ | NULL | |
| `error_message` | Text | NULL | 失败原因（FR-007 列表展示） |

> 与 `Sample` 分离存储：FR-009 三类数据隔离，删除时同步清除。

---

## 4. Embedding（嵌入向量，独立表）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | |
| `sample_id` | UUID | FK → sample.id, NOT NULL | |
| `chunk_index` | Integer | NOT NULL | 切片序号 |
| `chunk_text` | Text | NOT NULL | 原文（已 PII 处置） |
| `vector` | vector(1536) | NOT NULL | pgvector 字段 |
| `model_name` | String(64) | NOT NULL | embedding 模型名 |
| `created_at` | TimestampTZ | NOT NULL, DEFAULT now() | |

**索引**: `ivfflat` HNSW 索引在 `vector` 上（`m=16, ef_construction=64`）
**UNIQUE**: `(sample_id, chunk_index)`

---

## 5. Preference（偏好规则）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | String(16) | PK | 形如 `P-007`（SC-008 明示格式） |
| `owner_id` | UUID | FK → user.id, NOT NULL | 所有者 |
| `source_chains` | JSONB | NOT NULL | 来源片段链（§V 强制：样本/修改历史） |
| `rule_text` | Text | NOT NULL | 偏好规则自然语言描述 |
| `applies_to` | Enum(`cover`,`toc`,`body`,`closing`,`all`) | NOT NULL | 适用范围 |
| `apply_count` | Integer | NOT NULL, DEFAULT 0 | 应用次数 |
| `ignore_count` | Integer | NOT NULL, DEFAULT 0 | 被忽略次数（FR-014） |
| `last_applied_at` | TimestampTZ | NULL | |
| `is_active` | Boolean | NOT NULL, DEFAULT true | 生效状态（FR-013 用户可删除后改 false） |
| `created_at` | TimestampTZ | NOT NULL, DEFAULT now() | |
| `deleted_at` | TimestampTZ | NULL | 软删 |

**索引**: `(owner_id, is_active)`, `(owner_id, last_applied_at DESC)`

---

## 6. GenerationTask（生成任务）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | 任务唯一标识 |
| `owner_id` | UUID | FK → user.id, NOT NULL | 所有者 |
| `prompt` | Text | NOT NULL | 一句话原始需求 |
| `sample_snapshot_ids` | UUID[] | NOT NULL | 知识库快照（任务开始时锁定） |
| `status` | Enum(`queued`,`running`,`success`,`failed`,`cancelled`,`archived`) | NOT NULL, DEFAULT `queued` | 任务状态（Q3 答案新增 archived） |
| `current_stage` | Enum(`outline`,`points`,`svg`,`pptx`) | NULL | 当前阶段 |
| `queue_position` | Integer | NULL | 排队位置（FR-029） |
| `result_pptx_path` | String(512) | NULL | MinIO 最终文件路径 |
| `style_fit_score` | JSONB | NULL | FR-028 风格契合度三层分 |
| `token_consumed` | Integer | NOT NULL, DEFAULT 0 | Token 消耗 |
| `estimated_tokens` | Integer | NULL | FR-004 预估 |
| `estimated_seconds` | Integer | NULL | FR-004 预估 |
| `created_at` | TimestampTZ | NOT NULL, DEFAULT now() | |
| `started_at` | TimestampTZ | NULL | |
| `finished_at` | TimestampTZ | NULL | |
| `expires_at` | TimestampTZ | NULL | 180 天到期时间（FR-027） |
| `notified_at` | TimestampTZ | NULL | 到期前 14 天通知触达时间 |
| `queue_deadline_at` | TimestampTZ | NULL | 排队 5 分钟超时截止（FR-029） |
| `error_message` | Text | NULL | |

**索引**:
- `(owner_id, status, created_at DESC)` — 用户历史列表
- `(status, queue_position) WHERE status='queued'` — 调度器查询
- `(expires_at) WHERE status='success' AND expires_at IS NOT NULL` — 归档扫描

**状态机**:
```
queued ──[worker pick]──> running ──[all stages done]──> success ──[180d later]──> archived
   │                         │                              │
   │                         │                              └─[user delete]──> hard_deleted
   │                         ├──[stage fail]──> failed ──[user delete]──> hard_deleted
   │                         └──[user cancel]──> cancelled
   └─[5min timeout]──> cancelled
```

---

## 7. TraceStage（生成轨迹阶段）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | |
| `task_id` | UUID | FK → generation_task.id, NOT NULL | 所属任务 |
| `stage_name` | Enum(`outline`,`points`,`svg`,`pptx`) | NOT NULL | 阶段名（FR-015 至少 4 阶段） |
| `stage_order` | SmallInt | NOT NULL | 1-4 |
| `input_summary` | Text | NOT NULL | 输入摘要 |
| `output_summary` | Text | NOT NULL | 输出摘要 |
| `referenced_sample_ids` | UUID[] | NOT NULL, DEFAULT `[]` | 引用样本 ID |
| `duration_ms` | Integer | NOT NULL | 耗时 |
| `status` | Enum(`pending`,`running`,`success`,`failed`) | NOT NULL, DEFAULT `pending` | |
| `started_at` | TimestampTZ | NULL | |
| `finished_at` | TimestampTZ | NULL | |
| `error_message` | Text | NULL | |
| `redo_count` | Integer | NOT NULL, DEFAULT 0 | 重做次数（FR-016） |

**UNIQUE**: `(task_id, stage_name)`
**索引**: `(task_id, stage_order)`

---

## 8. SecurityEvent（安全事件）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | |
| `owner_id` | UUID | FK → user.id, NOT NULL | |
| `event_type` | Enum(`pii_hit`,`pii_blocked`,`pii_replaced`,`pii_acknowledged`,`unauth_access`,`bulk_export`,`bulk_delete`) | NOT NULL | |
| `hit_field` | String(64) | NULL | PII 命中的字段类型（手机/邮箱/身份证/客户名） |
| `action_taken` | Enum(`replace`,`block`,`allow`) | NOT NULL | 处置方式（FR-008 字段级 → replace 为主） |
| `related_resource_id` | UUID | NULL | 关联的 sample_id / task_id |
| `created_at` | TimestampTZ | NOT NULL, DEFAULT now() | |
| `details` | JSONB | NULL | 处置详情（原文片段 / 处置后） |

**索引**: `(owner_id, created_at DESC)`, `(event_type, created_at DESC)`

---

## 关键不变量（Invariants）

1. **三类数据强一致**: 删除 Sample → 同步删除 ParseResult + Embedding + 对应 SecurityEvent
2. **PII 双向追踪**: SecurityEvent 必须能反查到 Sample / Task
3. **偏好来源链必填**: Preference.source_chains 不允许为空（§V 强制）
4. **任务四阶段必填**: GenerationTask 终态时 TraceStage 必须有 4 条 success 记录
5. **队列位置一致性**: queued 状态必有 queue_position；running 必无
6. **到期时间唯一源**: GenerationTask.expires_at 由 created_at + 180d 派生，禁止外部写入
7. **样本解耦（US6）**: 删除 Sample 时 `slide_assets.source_sample_id` 设为 NULL 不级联删除，孤儿素材由用户决定去留；修改 DraftSlide 永不影响 SlideAsset 与 Sample（解耦三层）
8. **草稿单写者锁（US6）**: Draft.editor_user_id 字段非空时，其他用户 MUST 只读；自动保存由 editor_user_id 持有
9. **派生副本一致性（US6）**: DraftSlide.materialized JSON 唯一变化入口；SlideAsset 本身从不写

---

## US6 新增实体概览

> 对应 [spec.md](file:///f:/workspace/PPT_Agent/specs/001-mvp-closed-loop/spec.md) §User Story 6 + FR-030~FR-037。新增 4 张表 + 1 个 ENUM 增量。

| 实体 | 用途 | 关键关系 |
|------|------|----------|
| `slide_assets` | 从 sample 抽取的、按页为单位的独立素材资产 | → samples (source_sample_id, NULLable) |
| `drafts` | 用户正在编辑的工作 PPT（混合三种来源） | → users |
| `draft_slides` | 草稿中的单张页（保留来源溯源链） | → drafts, → slide_assets (reused), → trace_stages (generated) |
| `material_search_index` | 搜索加速索引（BM25 + 元数据筛选） | → slide_assets |

**新增 ENUM**：`slide_visual_type`（视觉类型）、`draft_status`（草稿状态）、`draft_slide_source_type`（来源类型）

---

## 演进计划

- M1：表 1-3, 6-7 落地（用户/样本/任务/轨迹）
- M2：表 4, 8, 9-12 落地（向量 + 安全事件 + **素材库 4 张表**）
- M3：表 5 落地（偏好规则）
- M4：归档/通知的定时任务与 Archive 状态机完善
- M5（US6 切片）：素材库 → 草稿拼装 → 导出三段串联验收

---

# Phase 2: 完整 PostgreSQL DDL

> 与 plan.md §Project Structure 配合，作为 `backend/src/db/migrations/versions/000X_*.py` 的源真值。

## 2.1 ENUM Types（统一枚举定义）

```sql
-- 用户订阅
CREATE TYPE user_tier AS ENUM ('personal', 'team', 'enterprise');

-- 样本文件类型
CREATE TYPE file_type AS ENUM ('pptx', 'pdf', 'docx');

-- 样本解析状态
CREATE TYPE parse_status AS ENUM ('pending', 'parsing', 'parsed', 'failed');

-- 偏好适用范围
CREATE TYPE preference_scope AS ENUM ('cover', 'toc', 'body', 'closing', 'all');

-- 偏好来源片段类型（用于 source_chains 强校验）
CREATE TYPE preference_source_type AS ENUM (
    'sample_pptx',       -- 来自样本 PPTX
    'manual_edit',       -- 来自用户手动改写
    'preference_apply'   -- 来自偏好应用后用户撤销
);

-- 生成阶段
CREATE TYPE task_stage AS ENUM ('outline', 'points', 'svg', 'pptx');

-- 生成任务状态
CREATE TYPE task_status AS ENUM (
    'queued', 'running', 'success', 'failed', 'cancelled', 'archived'
);

-- 阶段执行状态
CREATE TYPE stage_status AS ENUM ('pending', 'running', 'success', 'failed');

-- 安全事件类型
CREATE TYPE security_event_type AS ENUM (
    'pii_hit', 'pii_blocked', 'pii_replaced', 'pii_acknowledged',
    'unauth_access', 'bulk_export', 'bulk_delete'
);

-- 安全事件处置方式
CREATE TYPE security_action AS ENUM ('replace', 'block', 'allow');

-- ─── US6 新增 ENUM ───

-- 素材视觉类型（FR-030）
CREATE TYPE slide_visual_type AS ENUM (
    'cover',         -- 封面
    'toc',           -- 目录
    'architecture',  -- 架构图
    'flowchart',     -- 流程图
    'data',          -- 数据/图表
    'body',          -- 正文
    'closing',       -- 结语/封底
    'mixed'         -- 混合/无法分类
);

-- 草稿状态
CREATE TYPE draft_status AS ENUM (
    'active',        -- 编辑中
    'archived',      -- 归档
    'exported'       -- 已导出（保留 30 天后归档）
);

-- 草稿页来源类型
CREATE TYPE draft_slide_source_type AS ENUM (
    'reused',        -- 来自 SlideAsset
    'generated',     -- 来自 TraceStage（生成任务产物）
    'manual'         -- 手动创建
);
```

## 2.2 Tables（DDL）

### 2.2.1 users

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    display_name    VARCHAR(64)  NOT NULL,
    tier            user_tier    NOT NULL DEFAULT 'personal',
    active_sample_ids UUID[]     NOT NULL DEFAULT '{}',
    api_key_hash    VARCHAR(128) NOT NULL,  -- 兼容旧版；推荐使用 api_keys 表
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,

    CONSTRAINT users_email_lower_chk CHECK (email = lower(email))
);

CREATE INDEX idx_users_email      ON users (email) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_tier       ON users (tier);
CREATE INDEX idx_users_deleted_at ON users (deleted_at);
```

### 2.2.2 api_keys

```sql
CREATE TABLE api_keys (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash           VARCHAR(128) UNIQUE NOT NULL,
    key_prefix         VARCHAR(8)   NOT NULL,
    scopes             VARCHAR(64)[] NOT NULL DEFAULT ARRAY['generation:write']::VARCHAR(64)[],
    rate_limit_per_min INTEGER      NOT NULL DEFAULT 60,
    last_used_at       TIMESTAMPTZ,
    expires_at         TIMESTAMPTZ,
    revoked_at         TIMESTAMPTZ,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT api_key_prefix_chk CHECK (char_length(key_prefix) = 8),
    CONSTRAINT api_key_rate_chk   CHECK (rate_limit_per_min > 0 AND rate_limit_per_min <= 1000)
);

CREATE UNIQUE INDEX uk_api_keys_hash ON api_keys (key_hash);
CREATE INDEX idx_api_keys_owner      ON api_keys (owner_id) WHERE revoked_at IS NULL;
```

### 2.2.3 samples

```sql
CREATE TABLE samples (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file_name        VARCHAR(255) NOT NULL,
    file_hash        VARCHAR(64)  NOT NULL,   -- SHA-256
    file_type        file_type    NOT NULL,
    raw_path         VARCHAR(512) NOT NULL,   -- MinIO key
    parse_status     parse_status NOT NULL DEFAULT 'pending',
    parse_page_count INTEGER,
    pii_summary      JSONB,
    uploaded_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    parsed_at        TIMESTAMPTZ,
    deleted_at       TIMESTAMPTZ,

    CONSTRAINT samples_hash_chk CHECK (char_length(file_hash) = 64)
);

-- FR-010 同用户同 hash 去重（仅在未软删时生效）
CREATE UNIQUE INDEX uk_samples_owner_hash
    ON samples (owner_id, file_hash) WHERE deleted_at IS NULL;

CREATE INDEX idx_samples_owner_status
    ON samples (owner_id, parse_status) WHERE deleted_at IS NULL;
CREATE INDEX idx_samples_parse_pending
    ON samples (parse_status) WHERE parse_status IN ('pending', 'failed');
```

### 2.2.4 parse_results（独立表，FR-009 三类分离）

```sql
CREATE TABLE parse_results (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sample_id         UUID UNIQUE NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
    structure_json    JSONB       NOT NULL,
    parse_version     VARCHAR(16) NOT NULL,
    parse_started_at  TIMESTAMPTZ NOT NULL,
    parse_finished_at TIMESTAMPTZ,
    error_message     TEXT
);

CREATE INDEX idx_parse_results_sample ON parse_results (sample_id);
CREATE INDEX idx_parse_results_jsonb  ON parse_results USING GIN (structure_json);
```

### 2.2.5 embeddings（pgvector）

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE embeddings (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sample_id   UUID NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text  TEXT   NOT NULL,            -- 已 PII 处置
    vector      vector(1536) NOT NULL,      -- text-embedding-3-small
    model_name  VARCHAR(64) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT embeddings_chunk_idx_chk CHECK (chunk_index >= 0)
);

CREATE UNIQUE INDEX uk_embeddings_sample_chunk
    ON embeddings (sample_id, chunk_index);

-- HNSW 索引：m=16, ef_construction=64（MVP 100k chunk 规模下查询 < 50ms）
CREATE INDEX idx_embeddings_vector_hnsw
    ON embeddings USING hnsw (vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

### 2.2.6 preferences

```sql
CREATE TABLE preferences (
    id              VARCHAR(16) PRIMARY KEY,    -- 形如 'P-007'
    owner_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_chains   JSONB NOT NULL,             -- [{source_type, ref_id, snippet, ts}]
    rule_text       TEXT   NOT NULL,
    applies_to      preference_scope NOT NULL,
    apply_count     INTEGER NOT NULL DEFAULT 0,
    ignore_count    INTEGER NOT NULL DEFAULT 0,
    last_applied_at TIMESTAMPTZ,
    is_active       BOOLEAN  NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,

    CONSTRAINT preferences_id_chk   CHECK (id ~ '^P-[0-9]{3,}$'),
    CONSTRAINT preferences_chain_chk CHECK (jsonb_array_length(source_chains) >= 1)
);

CREATE INDEX idx_preferences_owner_active
    ON preferences (owner_id, last_applied_at DESC NULLS LAST)
    WHERE is_active = TRUE AND deleted_at IS NULL;
```

### 2.2.7 generation_tasks

```sql
CREATE TABLE generation_tasks (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    prompt               TEXT   NOT NULL,
    sample_snapshot_ids  UUID[] NOT NULL,
    status               task_status NOT NULL DEFAULT 'queued',
    current_stage        task_stage,
    queue_position       INTEGER,
    result_pptx_path     VARCHAR(512),
    style_fit_score      JSONB,
    token_consumed       INTEGER NOT NULL DEFAULT 0,
    estimated_tokens     INTEGER,
    estimated_seconds    INTEGER,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at           TIMESTAMPTZ,
    finished_at          TIMESTAMPTZ,
    expires_at           TIMESTAMPTZ,          -- created_at + 180d
    notified_at          TIMESTAMPTZ,          -- 到期前 14 天通知触达
    queue_deadline_at    TIMESTAMPTZ,          -- 入队 + 5min
    error_message        TEXT,

    CONSTRAINT tasks_queue_position_chk
        CHECK ((status = 'queued' AND queue_position IS NOT NULL AND queue_position > 0)
            OR (status <> 'queued' AND queue_position IS NULL)),
    CONSTRAINT tasks_prompt_len_chk CHECK (char_length(prompt) BETWEEN 1 AND 1000)
);

CREATE INDEX idx_tasks_owner_status_created
    ON generation_tasks (owner_id, status, created_at DESC);

-- 调度器扫表：FIFO 排队
CREATE INDEX idx_tasks_queued_fifo
    ON generation_tasks (created_at)
    WHERE status = 'queued';

-- 归档扫描：成功 + 未通知 + 已到期
CREATE INDEX idx_tasks_to_notify
    ON generation_tasks (expires_at)
    WHERE status = 'success' AND notified_at IS NULL;

CREATE INDEX idx_tasks_to_archive
    ON generation_tasks (expires_at)
    WHERE status = 'success' AND notified_at IS NOT NULL
      AND expires_at < now() - INTERVAL '14 days';
```

### 2.2.8 trace_stages

```sql
CREATE TABLE trace_stages (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id                UUID NOT NULL REFERENCES generation_tasks(id) ON DELETE CASCADE,
    stage_name             task_stage   NOT NULL,
    stage_order            SMALLINT     NOT NULL,
    input_summary          TEXT NOT NULL,
    output_summary         TEXT NOT NULL,
    referenced_sample_ids  UUID[] NOT NULL DEFAULT '{}',
    duration_ms            INTEGER      NOT NULL,
    status                 stage_status NOT NULL DEFAULT 'pending',
    started_at             TIMESTAMPTZ,
    finished_at            TIMESTAMPTZ,
    error_message          TEXT,
    redo_count             INTEGER      NOT NULL DEFAULT 0,

    CONSTRAINT trace_stages_order_chk   CHECK (stage_order BETWEEN 1 AND 4),
    CONSTRAINT trace_stages_duration_chk CHECK (duration_ms >= 0),
    CONSTRAINT trace_stages_redo_chk    CHECK (redo_count >= 0)
);

CREATE UNIQUE INDEX uk_trace_task_stage ON trace_stages (task_id, stage_name);
CREATE INDEX idx_trace_task_order       ON trace_stages (task_id, stage_order);
```

### 2.2.9 security_events

```sql
CREATE TABLE security_events (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type           security_event_type NOT NULL,
    hit_field            VARCHAR(64),
    action_taken         security_action NOT NULL,
    related_resource_id  UUID,           -- sample_id or task_id
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    details              JSONB
);

-- 按月分区（PG 12+ 优化海量日志）
CREATE TABLE security_events_y2026m06 PARTITION OF security_events
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

CREATE INDEX idx_security_owner_time
    ON security_events (owner_id, created_at DESC);
CREATE INDEX idx_security_event_type
    ON security_events (event_type, created_at DESC);
```

### 2.2.10 slide_assets（US6 素材库）

```sql
CREATE TABLE slide_assets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_sample_id    UUID REFERENCES samples(id) ON DELETE SET NULL,  -- FR-037 孤儿素材保留
    source_page_index   INTEGER NOT NULL,            -- 在源 sample 中的 1-based 页码
    visual_type         slide_visual_type NOT NULL,
    content_type        VARCHAR(16) NOT NULL,         -- svg / text / image / chart
    slide_title         VARCHAR(256),                -- 该页主标题（用于列表展示）
    text_content        TEXT,                        -- 抽取的纯文本（用于 BM25 全文检索）
    svg_payload         JSONB,                       -- 若 content_type=svg，存 SVG 原文
    structure_payload   JSONB,                       -- 该页的结构化摘要（版式/块/层级）
    thumbnail_url       TEXT,                        -- 缩略图（MinIO 路径）
    style_features      JSONB,                       -- 风格指纹：color_palette / font_family / layout_id
    industry_tags       VARCHAR(32)[] NOT NULL DEFAULT '{}',  -- 行业标签
    embedding           vector(1536),                -- 嵌入向量（语义检索用）
    is_orphan           BOOLEAN NOT NULL DEFAULT FALSE,       -- 源 sample 已删 → 标记孤儿
    is_archived         BOOLEAN NOT NULL DEFAULT FALSE,
    reuse_count         INTEGER NOT NULL DEFAULT 0,  -- 被草稿引用次数
    last_reused_at      TIMESTAMPTZ,
    materialized        BOOLEAN NOT NULL DEFAULT FALSE,       -- 是否被某 DraftSlide 派生
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT slide_assets_source_page_chk
        CHECK (source_page_index > 0 AND source_page_index < 10000),
    CONSTRAINT slide_assets_content_type_chk
        CHECK (content_type IN ('svg', 'text', 'image', 'chart'))
);

-- 关键索引
CREATE INDEX idx_slide_assets_owner_visual
    ON slide_assets (owner_id, visual_type, created_at DESC);
CREATE INDEX idx_slide_assets_owner_orphan
    ON slide_assets (owner_id) WHERE is_orphan = TRUE;
-- 全文检索（pg 全文索引；与嵌入向量召回互补）
CREATE INDEX idx_slide_assets_text_fts
    ON slide_assets USING gin (to_tsvector('simple', coalesce(text_content, '')));
-- 向量检索（IVFFlat，1000 行后再建）
-- CREATE INDEX idx_slide_assets_embedding ON slide_assets USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
-- 按源 sample 反查
CREATE INDEX idx_slide_assets_source
    ON slide_assets (source_sample_id, source_page_index) WHERE source_sample_id IS NOT NULL;
```

### 2.2.11 drafts（US6 草稿）

```sql
CREATE TABLE drafts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title               VARCHAR(256) NOT NULL DEFAULT 'Untitled Draft',
    status              draft_status NOT NULL DEFAULT 'active',
    overall_style       JSONB,                  -- 草稿整体风格聚类：color_palette / font_family / master_id
    editor_user_id      UUID REFERENCES users(id) ON DELETE SET NULL,  -- FR-035 单写者锁
    editor_lock_at      TIMESTAMPTZ,            -- 锁的获取时间（用于自动过期 30 分钟）
    last_saved_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_saved_revision BIGINT NOT NULL DEFAULT 0,  -- 乐观锁
    slide_count         INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at         TIMESTAMPTZ,
    exported_at         TIMESTAMPTZ,

    CONSTRAINT drafts_title_chk CHECK (char_length(title) > 0)
);

CREATE INDEX idx_drafts_owner_active
    ON drafts (owner_id, last_saved_at DESC) WHERE status = 'active';
```

### 2.2.12 draft_slides（US6 草稿页）

```sql
CREATE TABLE draft_slides (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id            UUID NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    slide_order         INTEGER NOT NULL,        -- 草稿内顺序号（1-based）
    source_type         draft_slide_source_type NOT NULL,
    -- 来源引用（按 source_type 三选一 + 必须有 source_attribution_text）
    source_asset_id     UUID REFERENCES slide_assets(id) ON DELETE SET NULL,    -- reused
    source_stage_id     UUID REFERENCES trace_stages(id) ON DELETE SET NULL,   -- generated
    -- 派生副本：所有用户修改都进这里
    materialized        JSONB NOT NULL,          -- { svg|text, style_overrides, ... }
    thumbnail_url       TEXT,
    style_normalized    BOOLEAN NOT NULL DEFAULT TRUE,    -- FR-034 风格归一开关
    normalized_failed   BOOLEAN NOT NULL DEFAULT FALSE,   -- 归一失败标记
    source_attribution  TEXT NOT NULL,           -- "来自样本 X 第 Y 页" / "AI 生成于任务 T" / "手动"
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT draft_slides_order_chk CHECK (slide_order > 0 AND slide_order < 10000),
    -- 三选一强校验
    CONSTRAINT draft_slides_source_chk CHECK (
        (source_type = 'reused'   AND source_asset_id IS NOT NULL) OR
        (source_type = 'generated' AND source_stage_id IS NOT NULL) OR
        (source_type = 'manual'   AND source_asset_id IS NULL AND source_stage_id IS NULL)
    )
);

CREATE INDEX idx_draft_slides_draft_order
    ON draft_slides (draft_id, slide_order);
CREATE INDEX idx_draft_slides_source_asset
    ON draft_slides (source_asset_id) WHERE source_asset_id IS NOT NULL;
CREATE INDEX idx_draft_slides_source_stage
    ON draft_slides (source_stage_id) WHERE source_stage_id IS NOT NULL;
```

### 2.2.13 material_search_index（US6 搜索加速）

```sql
-- 该表与 slide_assets 一对一；为保持单一真值，由触发器同步
CREATE TABLE material_search_index (
    slide_asset_id      UUID PRIMARY KEY REFERENCES slide_assets(id) ON DELETE CASCADE,
    owner_id            UUID NOT NULL,
    text_tsv            tsvector NOT NULL,        -- 与 slide_assets.text_content 同步
    visual_type         slide_visual_type NOT NULL,
    industry_tags       VARCHAR(32)[] NOT NULL DEFAULT '{}',
    reuse_count         INTEGER NOT NULL DEFAULT 0,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_material_search_text ON material_search_index USING gin (text_tsv);
CREATE INDEX idx_material_search_owner_type
    ON material_search_index (owner_id, visual_type, reuse_count DESC);
CREATE INDEX idx_material_search_industry
    ON material_search_index USING gin (industry_tags);
```

## 2.3 Triggers

```sql
-- 自动维护 expires_at（任务创建后 180 天；不可被显式 UPDATE 覆盖）
CREATE OR REPLACE FUNCTION set_task_expires_at() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.expires_at IS NULL THEN
        NEW.expires_at := NEW.created_at + INTERVAL '180 days';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tasks_set_expires
    BEFORE INSERT ON generation_tasks
    FOR EACH ROW EXECUTE FUNCTION set_task_expires_at();

-- updated_at 自动维护（示例：preferences）
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 注：当前数据模型未包含 updated_at 列；按需扩展。

-- ─── US6：slide_assets → material_search_index 同步触发器 ───
CREATE OR REPLACE FUNCTION sync_material_search_index() RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO material_search_index
        (slide_asset_id, owner_id, text_tsv, visual_type, industry_tags, reuse_count, updated_at)
    VALUES
        (NEW.id, NEW.owner_id,
         to_tsvector('simple', coalesce(NEW.text_content, '')),
         NEW.visual_type, NEW.industry_tags, NEW.reuse_count, now())
    ON CONFLICT (slide_asset_id) DO UPDATE
        SET text_tsv   = EXCLUDED.text_tsv,
            visual_type = EXCLUDED.visual_type,
            industry_tags = EXCLUDED.industry_tags,
            reuse_count = EXCLUDED.reuse_count,
            updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_slide_assets_sync_search
    AFTER INSERT OR UPDATE ON slide_assets
    FOR EACH ROW EXECUTE FUNCTION sync_material_search_index();

-- ─── US6：sample 删除 → 标记 slide_assets 为孤儿（不级联删除） ───
CREATE OR REPLACE FUNCTION mark_orphan_assets() RETURNS TRIGGER AS $$
BEGIN
    UPDATE slide_assets
        SET is_orphan = TRUE, source_sample_id = NULL, updated_at = now()
    WHERE source_sample_id = OLD.id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sample_delete_orphan_assets
    AFTER DELETE ON samples
    FOR EACH ROW EXECUTE FUNCTION mark_orphan_assets();

-- ─── US6：drafts 草稿单写者锁自动过期 ───
-- editor_lock_at 超过 30 分钟 → 自动释放（由后台 cron 调用，无需触发器）
-- 此处仅提供 SQL helper：
-- UPDATE drafts SET editor_user_id = NULL, editor_lock_at = NULL
-- WHERE editor_lock_at < now() - INTERVAL '30 minutes' AND status = 'active';
```

## 2.4 Row-Level Security (Constitution §IV 最小权限)

```sql
-- 多租户隔离：所有业务表强制 owner_id = current_setting('app.user_id')::uuid
ALTER TABLE samples        ENABLE ROW LEVEL SECURITY;
ALTER TABLE preferences    ENABLE ROW LEVEL SECURITY;
ALTER TABLE generation_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_events   ENABLE ROW LEVEL SECURITY;

CREATE POLICY samples_owner_isolation ON samples
    USING (owner_id = current_setting('app.user_id', TRUE)::uuid);

CREATE POLICY preferences_owner_isolation ON preferences
    USING (owner_id = current_setting('app.user_id', TRUE)::uuid);

CREATE POLICY tasks_owner_isolation ON generation_tasks
    USING (owner_id = current_setting('app.user_id', TRUE)::uuid);

CREATE POLICY security_owner_isolation ON security_events
    USING (owner_id = current_setting('app.user_id', TRUE)::uuid);

-- 应用层在每次请求前：
SET LOCAL app.user_id = '<uuid>';

-- ─── US6：素材与草稿的 RLS ───
ALTER TABLE slide_assets             ENABLE ROW LEVEL SECURITY;
ALTER TABLE drafts                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE draft_slides             ENABLE ROW LEVEL SECURITY;
ALTER TABLE material_search_index    ENABLE ROW LEVEL SECURITY;

CREATE POLICY slide_assets_owner_isolation ON slide_assets
    USING (owner_id = current_setting('app.user_id', TRUE)::uuid);

CREATE POLICY drafts_owner_isolation ON drafts
    USING (owner_id = current_setting('app.user_id', TRUE)::uuid);

-- draft_slides 通过所属 draft 的 owner_id 隔离
CREATE POLICY draft_slides_owner_isolation ON draft_slides
    USING (EXISTS (
        SELECT 1 FROM drafts d
        WHERE d.id = draft_slides.draft_id
          AND d.owner_id = current_setting('app.user_id', TRUE)::uuid
    ));

CREATE POLICY material_search_owner_isolation ON material_search_index
    USING (owner_id = current_setting('app.user_id', TRUE)::uuid);
```

---

# Phase 3: Pydantic v2 DTO（API 层契约）

> 与 `contracts/openapi.yaml` 一一对应，由 FastAPI 自动生成 OpenAPI schema。

```python
# backend/src/models/dto.py
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


# ─── Enums（与 PG ENUM 同步）───
class UserTier(str, Enum):
    PERSONAL = "personal"
    TEAM = "team"
    ENTERPRISE = "enterprise"


class FileType(str, Enum):
    PPTX = "pptx"
    PDF = "pdf"
    DOCX = "docx"


class ParseStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"


class TaskStage(str, Enum):
    OUTLINE = "outline"
    POINTS = "points"
    SVG = "svg"
    PPTX = "pptx"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class SecurityEventType(str, Enum):
    PII_HIT = "pii_hit"
    PII_BLOCKED = "pii_blocked"
    PII_REPLACED = "pii_replaced"
    PII_ACKNOWLEDGED = "pii_acknowledged"
    UNAUTH_ACCESS = "unauth_access"
    BULK_EXPORT = "bulk_export"
    BULK_DELETE = "bulk_delete"


# ─── Common ───
NonEmptyStr = Annotated[str, StringConstraints(min_length=1, max_length=1000)]


class StyleFitScore(BaseModel):
    """FR-028 三层客观指标，每类 ≥ 80% 视为该层契合。"""
    model_config = ConfigDict(frozen=True)
    layout: float = Field(..., ge=0, le=1, description="版式结构契合度")
    palette: float = Field(..., ge=0, le=1, description="配色分布契合度")
    font: float = Field(..., ge=0, le=1, description="字体族契合度")
    is_fit: bool = Field(..., description="三层全部 ≥ 0.8 时为 True")


# ─── Generation ───
class CreateGenerationRequest(BaseModel):
    prompt: NonEmptyStr = Field(..., description="FR-001 一句话需求")
    referenced_sample_ids: list[UUID] | None = Field(
        None, description="可选：限定本次任务使用的样本子集"
    )


class GenerationTaskDTO(BaseModel):
    id: UUID
    prompt: str
    status: TaskStatus
    current_stage: TaskStage | None
    queue_position: int | None
    result_pptx_url: str | None
    style_fit_score: StyleFitScore | None
    token_consumed: int
    estimated_tokens: int | None
    estimated_seconds: int | None
    created_at: datetime
    expires_at: datetime | None


# ─── Sample ───
class SampleDTO(BaseModel):
    id: UUID
    file_name: str
    file_type: FileType
    parse_status: ParseStatus
    parse_page_count: int | None
    pii_summary: dict | None
    uploaded_at: datetime


class BatchUploadResponse(BaseModel):
    accepted: int
    duplicates: int
    rejected: int
    samples: list[SampleDTO]


# ─── Preference ───
class PreferenceSourceChain(BaseModel):
    source_type: str  # sample_pptx / manual_edit / preference_apply
    ref_id: UUID
    snippet: str
    ts: datetime


class PreferenceDTO(BaseModel):
    id: str = Field(..., pattern=r"^P-\d{3,}$")
    rule_text: str
    applies_to: str
    apply_count: int
    ignore_count: int
    last_applied_at: datetime | None
    is_active: bool
    source_chains: list[PreferenceSourceChain]
    created_at: datetime


# ─── Trace ───
class TraceStageDTO(BaseModel):
    stage_name: TaskStage
    stage_order: int
    status: StageStatus
    input_summary: str
    output_summary: str
    duration_ms: int
    redo_count: int
    referenced_sample_ids: list[UUID]


class GenerationTraceDTO(BaseModel):
    task_id: UUID
    stages: list[TraceStageDTO]


# ─── Security ───
class SecurityEventDTO(BaseModel):
    id: UUID
    event_type: SecurityEventType
    hit_field: str | None
    action_taken: str
    related_resource_id: UUID | None
    details: dict | None
    created_at: datetime


# ─── US6：素材库 / 草稿 DTO ───
class SlideVisualType(str, Enum):
    COVER = "cover"
    TOC = "toc"
    ARCHITECTURE = "architecture"
    FLOWCHART = "flowchart"
    DATA = "data"
    BODY = "body"
    CLOSING = "closing"
    MIXED = "mixed"


class DraftStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    EXPORTED = "exported"


class DraftSlideSourceType(str, Enum):
    REUSED = "reused"
    GENERATED = "generated"
    MANUAL = "manual"


class SlideAssetDTO(BaseModel):
    """单张可复用素材。"""
    id: UUID
    owner_id: UUID
    source_sample_id: UUID | None = Field(None, description="源样本；为 NULL 表示孤儿素材")
    source_page_index: int = Field(..., ge=1, description="在源 sample 中的 1-based 页码")
    visual_type: SlideVisualType
    content_type: str = Field(..., description="svg / text / image / chart")
    slide_title: str | None
    text_content: str | None
    thumbnail_url: str | None
    industry_tags: list[str] = Field(default_factory=list)
    is_orphan: bool
    is_archived: bool
    reuse_count: int
    last_reused_at: datetime | None
    created_at: datetime
    # 仅详情接口返回：
    style_features: dict | None = None
    svg_payload: dict | None = None
    structure_payload: dict | None = None


class MaterialSearchRequest(BaseModel):
    """FR-031 素材库查询。"""
    query: str | None = Field(None, max_length=200, description="关键词；为空时只按筛选返回")
    visual_types: list[SlideVisualType] | None = None
    industry_tags: list[str] | None = None
    source_sample_ids: list[UUID] | None = None
    include_orphan: bool = False
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class MaterialSearchResult(BaseModel):
    items: list[SlideAssetDTO]
    total: int
    page: int
    page_size: int
    has_next: bool
    next_url: str | None = None


class StyleNormalizationRequest(BaseModel):
    """FR-034 风格归一参数。"""
    enable_normalize: bool = True
    target_style: dict = Field(..., description="草稿整体风格聚类：color_palette / font_family / layout_id")


class DraftSlideDTO(BaseModel):
    """草稿中的单张页（FR-033）。"""
    id: UUID
    slide_order: int = Field(..., ge=1)
    source_type: DraftSlideSourceType
    source_asset_id: UUID | None = None
    source_stage_id: UUID | None = None
    thumbnail_url: str | None = None
    style_normalized: bool
    normalized_failed: bool
    source_attribution: str = Field(..., description="人类可读的来源标注")


class DraftDTO(BaseModel):
    id: UUID
    title: str
    status: DraftStatus
    overall_style: dict | None
    editor_user_id: UUID | None
    last_saved_at: datetime
    slide_count: int
    created_at: datetime


class DraftDetailDTO(DraftDTO):
    slides: list[DraftSlideDTO]


class CreateDraftRequest(BaseModel):
    title: str = Field(default="Untitled Draft", max_length=256)
    initial_style: dict | None = Field(None, description="可选：手动指定整体风格")


class InsertDraftSlideRequest(BaseModel):
    """在草稿的指定位置插入一张页。"""
    slide_order: int = Field(..., ge=1)
    source_type: DraftSlideSourceType
    source_asset_id: UUID | None = None    # reused
    source_stage_id: UUID | None = None    # generated
    materialize_payload: dict | None = Field(None, description="manual 时必填")
    enable_style_normalize: bool = True
    expected_revision: int = Field(..., description="乐观锁；与 drafts.last_saved_revision 匹配才写入")


class UpdateDraftMetaRequest(BaseModel):
    """草稿元数据更新（标题 / 自动保存）。"""
    title: str | None = Field(None, max_length=256)
    overall_style: dict | None = None
    slides_snapshot: list[DraftSlideDTO] | None = None
    expected_revision: int


class DraftExportRequest(BaseModel):
    """FR-036 导出草稿为 PPTX。"""
    include_source_attribution: bool = True
    final_style_overrides: dict | None = None
    expected_revision: int


class DraftExportJobDTO(BaseModel):
    """导出任务的 202 响应。"""
    job_id: UUID
    status: str = Field(..., description="pending / running / ready / failed")
    download_url: str | None = None
    expires_at: datetime | None = None


# ─── Data Lifecycle ───
class DataExportRequest(BaseModel):
    include_raw: bool = True
    include_parse: bool = True
    include_preferences: bool = True


class DataExportResponse(BaseModel):
    job_id: UUID
    estimated_minutes: int
    download_url: str | None  # 完成后填充


class DataDeleteRequest(BaseModel):
    confirm_phrase: str = Field(..., description="二次确认：必须等于 'DELETE ALL MY DATA'")
    acknowledged_at: datetime
```

---

# Phase 4: 迁移序列（Alembic versions/）

| 版本 | 文件 | 阶段 | 关键变更 |
|------|------|------|----------|
| **0001** | `0001_init_users_and_api_keys.py` | M0 | users + api_keys 表 + RLS |
| **0002** | `0002_samples_and_parse.py` | M1 | samples + parse_results + UNIQUE(owner_id, file_hash) |
| **0003** | `0003_generation.py` | M1 | generation_tasks + trace_stages + 触发器 set_task_expires_at |
| **0004** | `0003b_embeddings.py` | M2 | pgvector extension + embeddings + HNSW 索引 |
| **0005** | `0004_security_events.py` | M2 | security_events + 月度分区（2026-06） |
| **0006** | `0005_preferences.py` | M3 | preferences + 序列 P-NNN |
| **0007** | `0006_index_tune.py` | M4 | 性能调优索引（如 `idx_tasks_archived`） |
| **0008** | `0007_materials_and_drafts.py` | **M5 (US6)** | slide_assets + drafts + draft_slides + material_search_index + 4 触发器 + RLS 增量 |

> **命名规则**（Constitution §VII）：`<seq>_<short_desc>.py`，seq 三位数字保证可排序。

---

# Phase 5: 种子数据 SQL（开发/测试）

```sql
-- backend/src/scripts/seed.sql — 由 seed_samples.py 执行
-- 5 类典型样本（与 tasks §T010 fixtures 对齐）

INSERT INTO samples (id, owner_id, file_name, file_hash, file_type, raw_path, parse_status, parse_page_count)
VALUES
    ('00000000-0000-0000-0000-000000000a01', '00000000-0000-0000-0000-0000000000a0',
     'q1_company_review.pptx', repeat('a',64), 'pptx', 'samples/q1_company_review.pptx', 'parsed', 18),
    ('00000000-0000-0000-0000-000000000a02', '00000000-0000-0000-0000-0000000000a0',
     'sales_training.pptx',     repeat('b',64), 'pptx', 'samples/sales_training.pptx',     'parsed', 24),
    ('00000000-0000-0000-0000-000000000a03', '00000000-0000-0000-0000-0000000000a0',
     'procurement_proposal.pptx', repeat('c',64), 'pptx', 'samples/procurement_proposal.pptx', 'parsed', 15),
    ('00000000-0000-0000-0000-000000000a04', '00000000-0000-0000-0000-0000000000a0',
     'quarterly_data_dashboard.pptx', repeat('d',64), 'pptx', 'samples/quarterly_data_dashboard.pptx', 'parsed', 20),
    ('00000000-0000-0000-0000-000000000a05', '00000000-0000-0000-0000-0000000000a0',
     'product_marketing.pptx', repeat('e',64), 'pptx', 'samples/product_marketing.pptx', 'parsed', 22)
ON CONFLICT (owner_id, file_hash) WHERE deleted_at IS NULL DO NOTHING;
```

---

# Phase 6: 数据生命周期图

```text
上传 Sample
    ├─ [pending] ── 解析 worker 拉取 ──> [parsing] ── 成功 ──> [parsed] ── 生成 Embedding
    │                                                    │
    │                                                    └─ 失败 ──> [failed] (重试 ≤ 3)
    └─ 软删 (deleted_at) ──> 7d 后硬删（CASCADE 同步清除 parse_results + embeddings + security_events）

发起 Generation
    └─ [queued] ── 调度器 FIFO ──> [running] ──> [success | failed | cancelled]
                                          └─> [success] ── 180d 后 ──> [archived] (MinIO 冷存储)

触发 PII 中间件
    └─ 写 security_events(action_taken='replace'|'block')
```

---

**Data Model Status**: ✅ Phase 1–6 全部完成（9 个实体、完整 DDL、DTO、迁移、种子、生命周期）
**Recommended Next Command**: 直接进入 `/speckit.implement` — T015（User ORM）、T016（alembic init）、T033–T035（US1 模型与迁移）等待此 schema 作为源真值。
