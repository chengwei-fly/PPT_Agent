# PPT_Agent 项目搭建与代码修复技术文档

> 本文档记录了从零搭建 PPT_Agent 项目的完整步骤，以及运行时发现并修复的所有问题。
> AI 可基于本文档复现搭建过程。

---

## 一、项目概览

| 层 | 目录 | 技术栈 |
|---|---|---|
| 后端 | `backend/` | Python 3.11 + FastAPI + SQLAlchemy 2.x (async) + Alembic |
| 前端 | `frontend/` | React 18 + TypeScript + Vite 5 + Tailwind CSS + Zustand + TanStack Query |
| AI 引擎 | `AgentScope/` | 多智能体编排框架（本地路径依赖） |
| 基础设施 | `infra/` | PostgreSQL 16 (pgvector) + Redis 7 + MinIO + Jaeger + Prometheus + Grafana |

### 访问地址

| 服务 | URL | 凭证 |
|------|-----|------|
| 前端 | http://localhost:5173 | — |
| 后端 API 文档 | http://localhost:8000/docs | — |
| MinIO 控制台 | http://localhost:9001 | minioadmin / minioadmin |
| Jaeger UI | http://localhost:16686 | — |
| Grafana | http://localhost:3000 | admin / admin |
| PostgreSQL | localhost:5432 | pptagent / pptagent |
| Redis | localhost:6379 | — |

---

## 二、环境依赖

### 2.1 必需软件

- **Python 3.11+** — 后端运行时
- **Node.js 20+** — 前端构建
- **pnpm 9+** — 前端包管理器（安装：`npm install -g pnpm@9`）
- **uv** — Python 包管理器（安装：`pip install uv`）
- **Docker Desktop** — 基础设施容器（WSL2 后端）

### 2.2 Docker 镜像

共需 7 个镜像，国内网络环境需通过镜像站拉取：

```bash
# 国内可用镜像站：docker.1panel.live
IMAGES=(
    "pgvector/pgvector:pg16"
    "library/redis:7-alpine"
    "minio/minio:latest"
    "minio/mc:latest"
    "jaegertracing/all-in-one:1.57"
    "prom/prometheus:v2.54.0"
    "grafana/grafana:11.1.0"
)

for img in "${IMAGES[@]}"; do
    docker pull "docker.1panel.live/$img"
    docker tag "docker.1panel.live/$img" "$img"
done
```

---

## 三、初始化步骤

### 3.1 环境变量

```bash
# 后端
cp backend/.env.example backend/.env

# 前端
cp frontend/.env.example frontend/.env
```

**backend/.env 关键配置**（DeepSeek 为例）：

```ini
APP_ENV=development
DATABASE_URL=postgresql+asyncpg://pptagent:pptagent@localhost:5432/pptagent
DATABASE_URL_SYNC=postgresql://pptagent:pptagent@localhost:5432/pptagent
REDIS_URL=redis://localhost:6379/0
S3_ENDPOINT=localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_HOT=ppt-hot
S3_BUCKET_COLD=ppt-cold
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
SECRET_KEY=<随机32字符>
OPENAI_API_KEY=sk-<你的DeepSeek API Key>
OPENAI_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_TEMPERATURE=0.2
PII_FIELDS=["phone","email","id_card","customer_name","address","bank_card"]
DEV_API_KEY=dev-key
DEV_USER_EMAIL=dev@pptagent.local
```

> **注意**：`PII_FIELDS` 必须是 JSON 数组格式，不能用逗号分隔。

### 3.2 Docker 基础设施

修改 `infra/docker-compose.yml`，将 volumes 改为 D 盘绑定挂载（可选）：

```yaml
volumes:
  - D:/docker-data/postgres:/var/lib/postgresql/data  # 原为 postgres_data 命名卷
  - D:/docker-data/redis:/data
  - D:/docker-data/minio:/data
  - D:/docker-data/grafana:/var/lib/grafana
```

启动：

```bash
cd infra && docker compose up -d
```

### 3.3 安装依赖

```bash
# 后端（先修复 pyproject.toml，见第四章）
cd backend && uv sync --extra dev

# 前端
cd frontend && pnpm install
```

### 3.4 数据库迁移

```bash
cd backend && uv run alembic upgrade head
```

### 3.5 启动服务

**终端 1 — 后端 API**：

```bash
cd backend && uv run uvicorn src.main:app --reload --port 8000
```

**终端 2 — Worker**：

```bash
cd backend && uv run python -m src.scheduler.run_worker
```

**终端 3 — 前端**：

```bash
cd frontend && pnpm dev
```

---

## 四、代码修复清单

以下是在搭建过程中发现并修复的全部问题。

### 4.1 pyproject.toml — 空 `[[tool.uv.index]]` 导致 uv sync 失败

**文件**: `backend/pyproject.toml:90`
**错误**: `TOML parse error: missing field 'url'`
**修复**: 删除空的 `[[tool.uv.index]]` 块，替换为注释。

```diff
- [[tool.uv.index]]
- # (none — all local)
+ # No additional index required — all local dependencies
```

### 4.2 缺少依赖 `psycopg2-binary`

**错误**: `ModuleNotFoundError: No module named 'psycopg2'`（Alembic 迁移需要同步 PostgreSQL 驱动）
**修复**: `uv add psycopg2-binary`

### 4.3 缺少依赖 `prometheus-client`

**错误**: `ModuleNotFoundError: No module named 'prometheus_client'`（API 路由导入失败）
**修复**: `uv add prometheus-client`

### 4.4 缺少依赖 `orjson`

**错误**: `AssertionError: orjson must be installed to use ORJSONResponse`
**修复**: `uv add orjson`

### 4.5 MinIO API 变更 — `ExpirationRule` → `Expiration`

**文件**: `backend/src/storage/minio.py:14`
**错误**: `ImportError: cannot import name 'ExpirationRule' from 'minio.lifecycleconfig'`
**原因**: minio 7.2.x 版本 API 变更，`ExpirationRule` 改为 `Expiration`，且需配合 `Rule` 类使用。

```diff
- from minio.lifecycleconfig import ExpirationRule, LifecycleConfig
+ from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule

- rule = ExpirationRule(days=settings.task_retention_days + settings.task_purge_delay_days)
- config = LifecycleConfig([rule])
+ exp = Expiration(days=settings.task_retention_days + settings.task_purge_delay_days)
+ rule = Rule(status="Enabled", expiration=exp, rule_id="expire-old-tasks")
+ config = LifecycleConfig([rule])
```

### 4.6 OpenTelemetry API 变更 — `trace.sampling` 模块不存在

**文件**: `backend/src/core/observability.py:84`
**错误**: `AttributeError: module 'opentelemetry.trace' has no attribute 'sampling'`
**修复**: 使用 `opentelemetry.sdk.trace.sampling.TraceIdRatioBased` 替代。

```diff
+ from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

- sampler=trace.sampling.get_sampler(
-     f"{settings.otel_traces_sampler}={settings.otel_traces_sampler_arg}"
- ),
+ sampler=TraceIdRatioBased(float(settings.otel_traces_sampler_arg)),
```

### 4.7 OTLP gRPC 连接阻塞启动

**文件**: `backend/src/core/observability.py:80-91`
**问题**: `OTLPSpanExporter` 初始化时建立 gRPC 通道可能阻塞数十秒。
**修复**: 开发环境跳过 exporter 创建，仅在生产环境启用。

```python
if settings.app_env not in ("development",):
    exporter = OTLPSpanExporter(...)
    provider.add_span_processor(BatchSpanProcessor(exporter))
```

### 4.8 SQLAlchemy `PostgresDsn` 类型转换

**文件**: `backend/src/db/session.py:38`
**错误**: `ArgumentError: Expected string or URL object, got PostgresDsn`
**修复**: Pydantic `PostgresDsn` 需显式转为字符串。

```diff
- settings.database_url,
+ str(settings.database_url),
```

### 4.9 Logger 参数格式不兼容

**文件**: `backend/src/db/session.py:52`
**错误**: `TypeError: Logger._log() got an unexpected keyword argument 'pool_size'`
**修复**: 标准 `logging.Logger.info()` 不接受额外关键字参数。

```diff
- logger.info("db_initialized", pool_size=settings.db_pool_size)
+ logger.info("db_initialized pool_size=%d", settings.db_pool_size)
```

### 4.10 Draft 模型缺失 `owner` relationship

**文件**: `backend/src/db/models/draft.py:60`
**错误**: `InvalidRequestError: Mapper 'Draft' has no property 'owner'`
**原因**: `User.drafts = relationship("Draft", back_populates="owner")` 但 Draft 未定义 `owner`。
**修复**: 在 Draft 模型中添加：

```python
owner = relationship("User", back_populates="drafts")
```

### 4.11 路由冲突 — `/styles` 和 `/modes` 被 `/{task_id}` 拦截

**文件**: `backend/src/api/generations.py:183-244`
**错误**: 请求 `/generations/styles` 返回 422（"styles" 不是有效 UUID）
**原因**: FastAPI 按注册顺序匹配路由，`/{task_id}` 在 `/styles` 之前定义。
**修复**: 将静态路由移到动态路由前面。

```python
# ✅ 正确顺序：静态路由在前
@router.get("/styles")
async def list_visual_styles(): ...

@router.get("/modes")
async def list_communication_modes(): ...

@router.get("/{task_id}")  # 动态路由在后
async def get_generation(task_id: uuid.UUID): ...
```

### 4.12 Vite 代理重写缺少 `/v1` 前缀

**文件**: `frontend/vite.config.ts:18`
**错误**: 前端调用 `/api/generations/styles` 返回 404
**原因**: Vite 代理将 `/api` 删掉，但后端路由注册为 `/api/v1/*`。

```diff
- rewrite: (p) => p.replace(/^\/api/, ""),
+ rewrite: (p) => p.replace(/^\/api/, "/api/v1"),
```

### 4.13 前端 POST 响应字段名不匹配

**文件**: `frontend/src/pages/GenerationPage.tsx:93`
**错误**: 调用 `/api/generations/undefined`（task_id 为 undefined）
**原因**: 后端返回 `{ task_id: "..." }`，前端读的是 `resp.data.id`。

```diff
- const resp = await api.post<GenerationTask>("/generations", body);
- navigate(`/generate/${resp.data.id}`);
+ const resp = await api.post<{ task_id: string; queue_position: number }>("/generations", body);
+ navigate(`/generate/${resp.data.task_id}`);
```

### 4.14 前端缺少 API Key 自动注入

**文件**: `frontend/src/services/api.ts`、`frontend/src/stores/auth.ts`
**错误**: 所有需认证的 API 调用返回 401
**修复**: 添加 `ensureDevAuth()` 函数，自动将 `dev-key` 写入 localStorage。

```typescript
const DEV_KEY = "dev-key";
function ensureDevAuth(): void {
  const raw = localStorage.getItem("pptagent.auth");
  if (!raw) {
    localStorage.setItem("pptagent.auth", JSON.stringify({ apiKey: DEV_KEY, email: "dev@pptagent.local" }));
  }
}
ensureDevAuth(); // 模块加载时执行
```

### 4.15 缺少 Worker 入口脚本

**文件**: `backend/src/scheduler/run_worker.py`（新建）
**问题**: 系统设计了 Redis Stream 消费者组，但没有独立 Worker 进程。
**修复**: 创建 `run_worker.py`，从 Redis Stream 持续拉取任务执行。

```python
# 核心逻辑
while not SHUTDOWN_FLAG:
    entry = await dequeue_generation_task(timeout_ms=2000)
    if entry is None:
        continue
    task_id = entry["task_id"]
    owner_id = entry["owner_id"]
    await process_generation_task(task_id, owner_id)
```

### 4.16 `datetime.utcnow()` → `datetime.now(timezone.utc)`

**文件**: 多个文件（worker.py, pipeline.py, generations.py）
**错误**: `TypeError: can't compare offset-naive and offset-aware datetimes`
**原因**: Python 3.11+ 禁止比较有时区和无时区的 datetime。`datetime.utcnow()` 返回 naive datetime。
**修复**: 全部替换为带时区的版本。

```diff
- from datetime import datetime
+ from datetime import datetime, timezone

- datetime.utcnow()
+ datetime.now(timezone.utc)
```

修复文件列表：
- `src/scheduler/worker.py`
- `src/services/generation/pipeline.py`
- `src/api/generations.py`

### 4.17 缺少 `credentials` 表迁移

**问题**: `Credentials` ORM 模型存在但无 Alembic 迁移，导致 `relation "credentials" does not exist`。
**修复**: 手动创建表后需生成迁移文件：

```sql
CREATE TABLE credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_type VARCHAR(64) NOT NULL,
    name VARCHAR(128) NOT NULL DEFAULT '',
    credential_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
```

---

## 五、LLM 配置

### 5.1 DeepSeek

```ini
OPENAI_API_KEY=sk-<your-key>
OPENAI_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

DeepSeek 兼容 OpenAI API 格式，无需改代码。

> **注意**：DeepSeek 不提供 Embedding API。代码中 embedder 调用失败时会自动 fallback 到 `_hash_embedding()`（确定性伪向量），不影响 PPT 生成。

### 5.2 OpenAI

```ini
OPENAI_API_KEY=sk-<your-key>
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

### 5.3 其他兼容 OpenAI 格式的 LLM

只需修改 `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`LLM_MODEL` 三个变量。

---

## 六、生成流水线架构

```
POST /api/v1/generations
  → create_generation()        # 创建任务 + 入队 Redis Stream
  → Worker 拉取任务
  → process_generation_task()
    → Pipeline.run()
      ├── Stage 1: outline    # LLM 生成 PPT 大纲
      ├── Stage 2: points     # LLM 提取要点
      ├── Stage 3: svg        # LLM 生成 SVG 代码  
      └── Stage 4: pptx       # SVG → PPTX 转换 + 上传 MinIO
```

- **并发控制**: 每用户最多 2 个并发任务（Redis 槽位机制）
- **超时**: 队列等待 5 分钟，单个任务 300 秒
- **认证**: `Authorization: Bearer <api-key>` 或 `X-Api-Key: <key>`（开发环境 `dev-key`）

---

## 七、常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| uv sync 失败 | pyproject.toml 有空 `[[tool.uv.index]]` | 删除该配置块 |
| alembic 报错 psycopg2 | 缺少同步 PG 驱动 | `uv add psycopg2-binary` |
| 启动 50 秒+ | OTLP gRPC 连接阻塞 | 开发模式跳过 exporter |
| API 返回 401 | 未传 API Key | 前端已自动注入 `dev-key` |
| API 返回 404（前端） | Vite 代理重写错误 | `/api` → `/api/v1` |
| API 返回 422（/styles） | 路由顺序导致误匹配 | 静态路由移到 `/{task_id}` 之前 |
| 任务一直 queued | Worker 未启动 | `uv run python -m src.scheduler.run_worker` |
| datetime 比较报错 | `utcnow()` 返回 naive datetime | 改为 `datetime.now(timezone.utc)` |

---

*最后更新: 2026-06-29*
