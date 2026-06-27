# Quickstart: PPTagent MVP 本地开发

**Branch**: `001-mvp-closed-loop` | **Date**: 2026-06-24
**目标**: 5 分钟内启动 PPTagent MVP 后端 + 前端 + 依赖服务。

---

## 0. 前置条件

| 工具 | 版本 | 验证 |
|------|------|------|
| Docker Desktop | ≥ 4.25 | `docker --version` |
| Docker Compose | v2.x | `docker compose version` |
| Node.js | 20 LTS | `node --version` |
| pnpm | ≥ 9 | `pnpm --version` |
| Python | 3.11+ | `python --version` |
| uv | ≥ 0.4 | `uv --version` |

---

## 1. 启动依赖服务（PostgreSQL + pgvector + Redis + MinIO）

```bash
cd infra
docker compose up -d
# 等待 healthcheck 通过（通常 20-40 秒）
docker compose ps
```

服务清单（见 `infra/docker-compose.yml`）:

| 服务 | 端口 | 凭证 |
|------|------|------|
| PostgreSQL + pgvector | 5432 | `pptagent / pptagent` |
| Redis 7 | 6379 | 无 |
| MinIO | 9000 / 9001 | `minioadmin / minioadmin` |
| jaeger (可选) | 16686 | 无 |

---

## 2. 启动后端

```bash
cd backend
uv sync                          # 安装锁定依赖
cp .env.example .env             # 编辑环境变量
uv run alembic upgrade head      # 数据库迁移
uv run python -m src.scripts.seed_samples  # 导入 5 种典型样本
uv run uvicorn src.main:app --reload --port 8000
```

健康检查：

```bash
curl http://localhost:8000/healthz
# {"status":"ok","queue_length":0}
```

---

## 3. 启动前端

```bash
cd frontend
pnpm install
cp .env.example .env             # VITE_API_BASE_URL=http://localhost:8000
pnpm dev
```

访问 http://localhost:5173 即可使用 MVP 闭环。

---

## 4. 端到端冒烟

```bash
# 4.1 上传样本（curl 模拟前端拖入）
curl -X POST http://localhost:8000/api/v1/samples/batch \
  -H "Authorization: Bearer dev-key" \
  -F "files=@../tests/fixtures/samples/汇报-template.pptx"

# 4.2 一句话生成
curl -X POST http://localhost:8000/api/v1/generations \
  -H "Authorization: Bearer dev-key" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"做一份 12 页 Q3 储能项目立项汇报"}'

# 返回 task_id，轮询：
curl http://localhost:8000/api/v1/generations/{task_id} \
  -H "Authorization: Bearer dev-key"
```

预期 5 分钟内 status=success，result_pptx_path 可下载。

---

## 5. CI 6 阶段流水线（Constitution §VI）

`.github/workflows/ci.yml` 6 阶段：

1. **lint** — `ruff check`（Python）+ `eslint`（TypeScript）
2. **unit** — `uv run pytest tests/unit`（覆盖率 ≥ 80%）
3. **contract** — `uv run pytest tests/contract`（Pact 提供者 + 消费者）
4. **e2e** — `pnpm playwright test`（含 5 种真实样本回归）
5. **security** — `bandit -r src`（Python）+ `npm audit`（Node）
6. **token-budget** — `uv run pytest tests/integration/test_token_budget.py`（验证 SC-001 / SC-009 阈值）

任何阶段失败 → 阻塞合并。

---

## 6. 关键路径

| 任务 | 文件 |
|------|------|
| 添加新的 PII 规则 | `backend/src/core/pii.py` |
| 修改生成阶段 | `backend/src/services/generation/pipeline.py` |
| 添加风格契合度指标 | `backend/src/services/scoring/{layout,palette,font}_scorer.py` |
| 前端新增页 | `frontend/src/pages/<name>.tsx` + `router/index.tsx` |
| OpenAPI 类型重新生成 | `cd frontend && pnpm gen:api` |

---

## 7. 调试小贴士

- **trace 链路**：访问 `http://localhost:16686`（jaeger UI），按 `request_id` 检索
- **PII 中间件命中**：访问前端"安全事件"页或 `GET /api/v1/security/events`
- **队列状态**：`GET /api/v1/ops/queue-status` 或 `redis-cli XLEN ppt:queue`
- **MinIO 归档**：`http://localhost:9001` 用 `minioadmin / minioadmin` 登录，bucket `ppt-cold`

---

**Quickstart Status**: ✅ 与 `docker-compose.yml` 配套；Phase 2 `/speckit.tasks` 将基于此输出。
