# PPT_Agent 精选素材库 — 运维部署手册

> 目标读者：在朋友电脑/服务器上**第一次**把 `PPT_Agent` 跑起来的人。
> 范围：把 `F:\PPT素材` 这类本地 PPT 文件灌入"精选素材库"，并能通过前端 `素材库 / 精选库` 看到。
> 本机**没有 Docker 也能完成素材抽取**（CLI 不依赖 Redis/MinIO 的可选部分），但要看到前端缩略图仍需后端 + DB 完整运行。

---

## 0. 总览

精选素材库 = `slide_assets` 表中 `source_sample_id IS NULL` + `metadata_json.curated = true` 的那批行。
对所有用户可见，灌入的路径有 3 条：

| 路径 | 触发方式 | 适合场景 |
| ---- | -------- | -------- |
| **后端 CLI** | `python -m src.scripts.import_material_library --src <dir>` | 本机/无前端时灌入；CI/批处理；本仓库默认路径 |
| **后端 Admin API** | `POST /api/v1/admin/material-library/import` (multipart) | 部署到服务器后，通过前端"导入 PPT"按钮调用 |
| **后端 Admin API 目录模式** | `POST /api/v1/admin/material-library/import-dir` | 服务器上有整目录素材时 |

前端入口：`素材库` 页面右上角 **导入 PPT** 按钮（仅在持有 `X-Admin-Token` 时真正生效，详见 §4）。

---

## 1. 前置依赖（朋友电脑一次装好即可）

按顺序装，每个都用默认安装。

| 组件 | 版本 | 用途 | 备注 |
| ---- | ---- | ---- | ---- |
| **Docker Desktop** | 4.x+ | 跑 PostgreSQL/Redis/MinIO/Jaeger | 必须开启 WSL2 后端（Win11）或 Hyper-V（Win10） |
| **Python** | 3.11+ | 后端 | 勾选 *Add to PATH* |
| **uv** | 最新 | Python 包管理 | `pip install uv` 或 `winget install astral-sh.uv` |
| **Node.js** | 20 LTS+ | 前端 | 勾选 *npm* |
| **pnpm** | 9+ | 前端包管理 | `npm install -g pnpm` |
| **Git** | 2.40+ | 拉取代码 | 装 Git for Windows |
| **LibreOffice**（可选） | 7+ | 解析 `.ppt` 老格式 | 没装也不影响 `.pptx`；只在 `.ppt` 上才需要 |

> 已装过的可以跳过。装完打开新终端执行 `docker --version` / `python --version` / `node --version` / `pnpm --version` 验证。

---

## 2. 拉代码 + 改 `infra/docker-compose.yml` 的本地卷路径（**重要**）

`infra/docker-compose.yml` 默认把所有数据卷 bind mount 到 `D:/docker-data/...`。
**朋友电脑的 D 盘不一定存在**，必须改成实际盘符，否则 `docker compose up` 会直接报"找不到目录"或容器一直 restart。

```yaml
# infra/docker-compose.yml —— 搜索替换
volumes:
  - D:/docker-data/postgres:/var/lib/postgresql/data   # ← 改成你机器的目录，例如 E:/docker-data/postgres
  - D:/docker-data/redis:/data
  - D:/docker-data/minio:/data
  - D:/docker-data/grafana:/var/lib/grafana
```

建议**先一次性创建**这些空目录，否则 Docker 在 Win 上会按 root 创建，后面 rm 不掉：

```powershell
New-Item -ItemType Directory -Force -Path E:\docker-data\postgres
New-Item -ItemType Directory -Force -Path E:\docker-data\redis
New-Item -ItemType Directory -Force -Path E:\docker-data\minio
New-Item -ItemType Directory -Force -Path E:\docker-data\grafana
```

---

## 3. 启动基础设施（**必做**）

```powershell
cd infra
docker compose up -d
docker compose ps
```

正常应该看到 `postgres` / `redis` / `minio` / `jaeger` 全部 `healthy`，`minio-init` 已 `exited 0`。
要看的端口：

| 端口 | 服务 | 验证方式 |
| ---- | ---- | -------- |
| 5432 | Postgres + pgvector | `psql -h localhost -U pptagent -d pptagent`（密码 `pptagent`） |
| 6379 | Redis | `redis-cli -h localhost ping` → `PONG` |
| 9000 / 9001 | MinIO / MinIO Console | 浏览器 `http://localhost:9001` (`minioadmin` / `minioadmin`) |
| 16686 | Jaeger UI | 浏览器 `http://localhost:16686` |

任一服务一直 restart，立刻 `docker compose logs <svc>` 看报错。**90% 情况都是 §2 的卷路径没改对。**

---

## 4. 后端 `.env` 配置（**必做，缺一不可**）

```powershell
cd ..\backend
copy .env.example .env       # Windows
# cp .env.example .env       # WSL/Linux
notepad .env                # 编辑
```

需要确认 / 改动的键（**只列必须看的，其余保持默认**）：

```ini
# ─── 必填：LLM 密钥（没有就只跑启发式分类）────────────────
OPENAI_API_KEY=sk-replace-with-real-key        # 改成你/朋友的真实 key
OPENAI_BASE_URL=https://api.openai.com/v1       # 国内用硅基流动/DeepSeek 等兼容端点
LLM_MODEL=gpt-4o-mini
# 多模态分类（可选，留空 = 用 LLM_MODEL）
CURATED_LIBRARY_MULTIMODAL_MODEL=

# ─── 精选库开关 ────────────────────────────────────────
CURATED_LIBRARY_ENABLED=true
CURATED_LIBRARY_USE_LLM=false                   # 第一次先 false，用启发式跑通再切
CURATED_LIBRARY_MAX_ASSETS_PER_RUN=0            # 0 = 不限
```

> **没填 `OPENAI_API_KEY` 也能跑素材库**——`HeuristicClassifier` 用关键字规则兜底，封面/流程/架构等都能大致分对，只是标题/标签质量差一些。

其余默认值（数据库/Redis/MinIO/端口）只要 `docker compose` 起来了就**不要动**。

---

## 5. 安装后端 + 跑迁移

```powershell
uv sync --extra dev
uv run alembic upgrade head
uv run python -m src.scripts.seed_samples      # 可选：灌 5 个示例样本
```

`alembic upgrade head` 应该输出 `Running upgrade ... -> <head>, head`。
报错 `connection refused` → 第 3 步基础设施没起来；报错 `password authentication failed` → `.env` 里 `DATABASE_URL` 被手改了，回滚成 `pptagent:pptagent@localhost:5432/pptagent`。

---

## 6. **核心**：灌入 `F:\PPT素材`

### 路径 A — 本机 CLI（**最稳，推荐第一次用**）

```powershell
cd backend

# 1) 干跑 — 不写库，先看抽取了多少素材、分类得对不对
uv run python -m src.scripts.import_material_library `
    --src "F:\PPT素材" `
    --dry-run --max-assets 20

# 2) 真正写库
uv run python -m src.scripts.import_material_library `
    --src "F:\PPT素材"

# 3) 想要 LLM 精分类
uv run python -m src.scripts.import_material_library `
    --src "F:\PPT素材" --use-llm --llm-model gpt-4o-mini
```

成功输出（节选）：

```
============================================================
Curated material import
============================================================
  Files seen:      7
  Files failed:    0
  Assets extracted: 84
  Inserted:        84
  Updated:         0
  Skipped:         0

  Classification breakdown:
  llm         : 80
  heuristic   : 4
  visual_type:
  body        : 42
  flowchart   : 21
  data        : 12
  cover       : 9
============================================================
```

`--reset` 标志会**硬删**所有现有精选素材后再灌（**DESTRUCTIVE**，慎用）。

### 路径 B — 前端"导入 PPT"按钮

走这条要先把后端启起来：

```powershell
# 终端 1 — 后端
cd backend
uv run uvicorn src.main:app --reload --port 8000

# 终端 2 — 前端
cd frontend
pnpm install
pnpm dev
```

打开 `http://localhost:5173` → 登录（开发模式填 `dev-key` / `dev@pptagent.local`） → 左侧导航 **素材库** → 右上角 **导入 PPT** → 选 `.pptx` / `.ppt` 文件。
后端会写到：

```
POST /api/v1/admin/material-library/import
Headers: X-Admin-Token: <settings.dev_api_key>
Body:    multipart/form-data; file=@xxx.pptx
```

前端默认发 `X-Admin-Token: dev-key`（来自 `VITE_ADMIN_TOKEN` 或硬编码 dev-key）。

### 路径 C — 服务端整目录导入

```powershell
curl -X POST "http://localhost:8000/api/v1/admin/material-library/import-dir?path=F:/PPT素材" `
     -H "X-Admin-Token: dev-key" `
     -H "Content-Type: application/json" `
     -d '{"use_llm": false, "dry_run": false}'
```

---

## 7. 验证 — 看到的就是它了

```powershell
# 1) 统计
curl -H "X-Admin-Token: dev-key" `
     http://localhost:8000/api/v1/admin/material-library/stats
# 期望: {"total": 84, "by_visual_type": {...}, ...}

# 2) 前端检索（精选库 Tab，scope=curated）
浏览器: http://localhost:5173/materials
# 切换顶部 Tab: 精选库 / 我的素材 / 全部
```

`素材库` 页右上角徽章会显示 `精选 N 个 · YYYY-MM-DD 更新`。

---

## 8. 排错速查（按出现概率排序）

| 现象 | 原因 | 修法 |
| ---- | ---- | ---- |
| `docker compose up` 一直 restarting | 卷路径 `D:/docker-data/...` 不存在 | 见 §2，改成本地盘符 |
| 后端启动报 `connection to server at "localhost", port 5432 failed` | Postgres 容器没起 | `docker compose ps`；日志 `docker compose logs postgres` |
| `openai_api_key=sk-replace` 校验失败 | 没改 `.env` | 改成真 key；或保留 key 但 `CURATED_LIBRARY_USE_LLM=false` |
| 灌库时 `Files failed: 1` 且 `legacy_ppt_convert_failed` | `.ppt` 老格式，本机没装 LibreOffice/PowerPoint | 装 LibreOffice，或把 `.ppt` 另存为 `.pptx` |
| 灌库全部走 `heuristic` 但想用 LLM | `.env` 里 `CURATED_LIBRARY_USE_LLM=false` 或 `OPENAI_API_KEY` 未设置 | 改 `.env` 后**重启后端**（Pydantic settings 启动时加载） |
| 前端 `导入 PPT` 按钮 403 | 后端 `dev_api_key` 不等于 `dev-key` | 改前端 `VITE_ADMIN_TOKEN` 或后端 `DEV_API_KEY` |
| 前端缩略图 404 | MinIO 桶没创建 | 重新 `docker compose up -d minio-init`，或浏览器开 `http://localhost:9001` 看 `ppt-hot` 桶 |
| `alembic upgrade head` 报 `column ... does not exist` | 跳版本了 | `alembic downgrade base && alembic upgrade head` |
| LLM 调用 429 / quota | key 余额 | 切 `CURATED_LIBRARY_MULTIMODAL_MODEL=qwen-vl-max` 等国内端点 |

---

## 9. 朋友电脑上的"一次性"清单（推荐做成 checklist）

- [ ] 装 Docker Desktop（开 WSL2 后端）
- [ ] 装 Python 3.11+ / uv / Node 20+ / pnpm 9+
- [ ] 拉代码：`git clone https://github.com/<owner>/PPT_Agent.git`
- [ ] `infra/docker-compose.yml` 卷路径改成自己电脑的盘符
- [ ] `docker compose -f infra/docker-compose.yml up -d`
- [ ] `docker compose ps` 全部 healthy / exited 0
- [ ] `cd backend && cp .env.example .env && notepad .env` 填 `OPENAI_API_KEY`
- [ ] `uv sync --extra dev`
- [ ] `uv run alembic upgrade head`
- [ ] `uv run python -m src.scripts.import_material_library --src "F:\PPT素材" --dry-run --max-assets 20`
- [ ] `uv run python -m src.scripts.import_material_library --src "F:\PPT素材"`
- [ ] 启后端 `uv run uvicorn src.main:app --reload --port 8000`
- [ ] 启前端 `cd ../frontend && pnpm install && pnpm dev`
- [ ] 浏览器 `http://localhost:5173` 登录进 **素材库** → 切到 **精选库** Tab → 看到缩略图

---

## 10. 部署到云端（什么时候再考虑）

- 后端镜像：参考 `backend/Dockerfile`，`docker build -t pptagent-backend .`
- 把 `OPENAI_API_KEY` / `SECRET_KEY` / `DATABASE_URL` 等敏感值放进云 Secret Manager，**不要提交到 git**
- 精选库灌入建议作为一次性 init 任务，跑在 `docker compose run --rm backend python -m src.scripts.import_material_library --src /materials/curated/ --reset`

---

## 11. 关键运维配置速记（出问题对照）

| 关键变量 | 含义 | 缺省/推荐 |
| -------- | ---- | --------- |
| `DEV_API_KEY` | 管理员 Token（前端用 `X-Admin-Token` 发送） | `dev-key`（dev）/ 强随机（prod） |
| `SECRET_KEY` | JWT 签名密钥 | ≥ 32 字符，prod 必须随机 |
| `OPENAI_API_KEY` | LLM 鉴权 | dev 留 `sk-replace` 时禁用 LLM |
| `OPENAI_BASE_URL` | 兼容端点 | 默认 OpenAI，国内用 `https://api.siliconflow.cn/v1` 等 |
| `CURATED_LIBRARY_ENABLED` | 精选库总开关 | `true` |
| `CURATED_LIBRARY_USE_LLM` | 优先用 LLM 分类 | dev 留 `false` 跑通再切 `true` |
| `CURATED_LIBRARY_MULTIMODAL_MODEL` | 多模态模型 | 留空 = `LLM_MODEL` |

---

> 一句话：**本机没 Docker 不影响素材抽取（CLI 单跑）**；要让前端看到缩略图必须把后端 + DB + MinIO 拉起来，按 §3-§7 顺序走完即可。
