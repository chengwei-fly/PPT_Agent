# PPT_Agent 精选素材库 — 代码库 / 库内通用使用手册

> 这篇是给**改这套素材库代码 / 想把它拆出来当通用库**的同事看的。
> 部署/运维相关请看 [`MATERIAL_LIBRARY_OPS.md`](./MATERIAL_LIBRARY_OPS.md)。

---

## 1. 设计目标

把"团队共享的 PPT 素材包（图标、流程图、模板页、地图、关系图…）"作为一等公民纳入 `slide_assets` 表，
**对所有用户可见、按 hybrid 检索、保留 PPT 来源信息**。
代码层面**不引入新表**——复用 `slide_assets` + `metadata_json.curated = true` 这一个 bit。

约束：

- **零 schema 迁移**：用 `metadata_json` 的 JSONB 存 curated 元数据；幂等键 `(source_file, page_index, shape_name)` 也走 JSONB
- **LLM 可选**：无 key 时自动降级 `HeuristicClassifier`
- **可中断 / 可恢复**：每个 asset 独立 try/except 写库，partial import 也能 commit
- **解耦三层**：extractor (无 IO) → classifier (可替换) → importer (写库 + MinIO)
- **同包导入即用**：`from src.services.material_importer import PPTXExtractor, classify_asset, CuratedImporter`

---

## 2. 目录结构

```
backend/src/services/material_importer/
├── __init__.py        # 统一导出：extractor / classifier / importer
├── extractor.py       # PPTX → ExtractedAsset[]（含 .ppt 兼容 + 兜底渲染）
├── classifier.py      # LLMClassifier + HeuristicClassifier + classify_asset 工厂
└── importer.py        # CuratedImporter — 编排 extract → classify → 写库 + MinIO

backend/src/scripts/
└── import_material_library.py  # CLI 入口（可直接 python -m 跑）

backend/src/api/
└── admin.py           # /admin/material-library/*  (HTTP)

frontend/src/pages/
└── MaterialLibraryPage.tsx  # 精选库/我的/全部 Tab + 上传按钮

frontend/src/hooks/
└── useMaterials.ts    # useMaterials / useCuratedImport / useCuratedStats
```

---

## 3. 三层职责一览

### 3.1 `extractor.py` — `PPTXExtractor` / `ExtractedAsset` / `extract_from_file`

不依赖 DB / LLM / 网络，纯 CPU。

```python
from src.services.material_importer import PPTXExtractor, ExtractedAsset

extractor = PPTXExtractor(thumb_max_width=480)  # 缩略图最大宽
assets: list[ExtractedAsset] = extractor.extract("F:/PPT素材/咨询模板.pptx")

for a in assets:
    print(a.source_file, a.slide_index, a.shape_name)
    print("  size:", a.width, "x", a.height)
    print("  palette:", a.palette)
    print("  text head:", (a.text or "")[:60])
    # a.image_bytes 是 JPEG 缩略图 (max 480 wide), a.image_ext 是原始扩展名
```

支持的输入：

- `.pptx`：原生支持，提取每页 picture shape
- `.ppt`：通过 `convert_legacy_ppt()` → LibreOffice headless 或 PowerShell COM 转 `.pptx` 后再处理
- 单页没有 picture shape 时：兜底渲染整页到 PNG（用于 Roland Berger 这种纯 DrawingML 模板页）

### 3.2 `classifier.py` — `LLMClassifier` / `HeuristicClassifier`

```python
from src.services.material_importer import classify_asset, ClassificationResult

result: ClassificationResult = await classify_asset(asset, prefer_llm=True)
# result.visual_type : SlideVisualType enum
# result.title       : str | None
# result.industry_tags : list[str]    (≤5)
# result.used        : "llm" | "heuristic" | "llm-failed"
```

实现细节：

- `LLMClassifier.complete_json_vision` 走 `LLMClient.complete_vision`（OpenAI 兼容多模态），返回 JSON；带 ` ```json ` / `{...}` 兜底解析
- `HeuristicClassifier` 关键字表（`_KEYWORD_RULES` / `_TAG_KEYWORDS`）覆盖中英文"封面/目录/架构/流程/数据/正文/结尾"+ 行业标签（物流/地图/图标/关系图…）
- 工厂 `classify_asset(asset, prefer_llm)` 自动选 LLM 或 heuristic；key 缺/为占位符 `sk-replace` 时一律走 heuristic
- 进程内 LRU cache：`make_cached_classify()`，key = `(source_file, slide_index, shape_name, sha256(image_bytes)[:16])`

替换为别的分类器：实现 `MaterialClassifier` 接口（`async def classify(asset) -> ClassificationResult`），传入 `CuratedImporter(use_llm=...)` 之前替换 `_classify` 即可。

### 3.3 `importer.py` — `CuratedImporter` / `import_directory` / `drop_curated_assets`

```python
from src.services.material_importer import CuratedImporter
from src.db.session import get_session_factory

factory = get_session_factory()
async with factory() as session:
    importer = CuratedImporter(
        session,
        use_llm=False,                # 走 heuristic
        llm_model="qwen-vl-max",      # 实际模型，仅当 use_llm=True 时使用
        concurrency=4,                # 并发数（仅 LLM 路径生效）
    )
    report = await importer.import_directory(
        "F:/PPT素材",
        dry_run=False,
        max_assets=None,              # None = 不限
        auto_convert_legacy=True,     # 自动 .ppt → .pptx
    )
    await session.commit()
```

`ImportReport` 字段：

```python
@dataclass
class ImportReport:
    files_seen: int
    files_failed: int
    assets_extracted: int
    assets_inserted: int
    assets_updated: int
    assets_skipped: int
    classification_counts: dict[str, int]   # 含 "llm"/"heuristic" 与 "vt:cover" 等
    failures: list[str]                     # 首 50 条失败
    inserted_ids: list[str]
    started_at / finished_at: datetime
```

幂等逻辑（关键）：以 `metadata_json.source_file + shape_name + page_index` 三个键定位已存在行，命中则 update 而非 insert。

---

## 4. 完整使用示例

### 4.1 只跑一遍，不接 DB（验证 extractor 好不好用）

```python
from src.services.material_importer import PPTXExtractor

extractor = PPTXExtractor()
for f in ["F:/PPT素材/icons.pptx", "F:/PPT素材/flow.pptx"]:
    for a in extractor.extract(f):
        print(f"{a.source_file} #{a.slide_index} {a.shape_name} "
              f"({a.width}x{a.height}) palette={a.palette[:3]}")
```

### 4.2 仅写库：把一个目录彻底灌入

```python
import asyncio
from src.core.lifespan import init_db, dispose_db
from src.db.session import get_session_factory
from src.services.material_importer import import_directory

async def main():
    await init_db()
    try:
        factory = get_session_factory()
        async with factory() as session:
            report = await import_directory(
                session,
                "F:/PPT素材",
                use_llm=False,        # 先 heuristic 跑通
                dry_run=False,
            )
            await session.commit()
            print(report.to_dict())
    finally:
        await dispose_db()

asyncio.run(main())
```

### 4.3 替换为自己的分类器

```python
from src.services.material_importer import (
    CuratedImporter, MaterialClassifier, ClassificationResult, ExtractedAsset,
)

class MyClassifier(MaterialClassifier):
    async def classify(self, asset: ExtractedAsset) -> ClassificationResult:
        # 你自己的逻辑
        return ClassificationResult(
            visual_type=...,
            title=...,
            industry_tags=[...],
            used="custom",
        )

# Inject
importer = CuratedImporter(session, use_llm=False)
importer._classify = MyClassifier().classify
```

### 4.4 清空精选库（重建前）

```python
from src.services.material_importer import drop_curated_assets
from src.db.session import get_session_factory

async with get_session_factory()() as session:
    n = await drop_curated_assets(session)
    await session.commit()
    print(f"Deleted {n} curated assets")
```

---

## 5. HTTP API（前端集成）

所有 admin 端点要求 `X-Admin-Token: <settings.dev_api_key>`，默认 dev = `dev-key`。

| Method | Path | 说明 |
| ------ | ---- | ---- |
| `POST` | `/api/v1/admin/material-library/import` | 上传单个 PPT/PPTX，multipart `file` |
| `POST` | `/api/v1/admin/material-library/import-dir?path=...` | 服务端目录批量导入 |
| `GET`  | `/api/v1/admin/material-library/stats` | 数量统计（总数 + 按 visual_type + 按 source_file + last_import_at） |
| `POST` | `/api/v1/admin/material-library/reset` | **DESTRUCTIVE** 硬删所有精选素材 |
| `POST` | `/api/v1/admin/material-library/reembed` | 重新算 embedding |

`/api/v1/materials?scope=curated|mine|all` —— 检索端点按 scope 过滤：

- `curated`：所有用户的精选库（默认 `include_orphan=true`）
- `mine`：当前用户自己上传的样本里的素材
- `all`：以上两者并集（默认行为）

---

## 6. 配置（`.env` / `Settings`）

| 变量 | 默认 | 含义 |
| ---- | ---- | ---- |
| `CURATED_LIBRARY_ENABLED` | `true` | 总开关；`false` 时 importer 仍可跑但产物 `metadata_json.curated=false` |
| `CURATED_LIBRARY_USE_LLM` | `false` | `true` 时优先用 LLM 分类（仍会因无 key 自动降级） |
| `CURATED_LIBRARY_MULTIMODAL_MODEL` | 空 | 多模态模型；空 = 用 `LLM_MODEL` |
| `CURATED_LIBRARY_MAX_ASSETS_PER_RUN` | `0` | 每次 run 最多插入多少行；0 = 不限（admin API 受此约束，CLI 不） |
| `DEV_API_KEY` | `dev-key` | 前端 `X-Admin-Token` 默认值 |

---

## 7. 失败模式 / 已知坑

1. **`Pillow` 不支持 EMF 转换（在非 Windows 平台）** — extractor 记 warning 并跳过该图。
2. **`.ppt` 转 `.pptx` 失败** — 没装 LibreOffice 也没装 PowerPoint，CLI 会报 `RuntimeError`；把 `.ppt` 另存为 `.pptx` 是最稳的修法。
3. **LLM 慢 / 超时** — `concurrency` 调小（4→2）；或临时 `CURATED_LIBRARY_USE_LLM=false`。
4. **重复灌入会更新而不是新增** — 这是设计：避免库膨胀；要重建请 `--reset` 或调 `drop_curated_assets`。
5. **MinIO 不可用** — `thumb_key` / `original_key` 写不进去时该 asset 整体跳过（不进库），看 `ImportReport.failures`。
6. **embedding 不可用** — 同样 skip；前端 `素材库` 仍能用 keyword 搜索，只是缺向量召回。
7. **DB 字符集** — 标题/标签存中文/emoji 都行，要求 `client_encoding=UTF8`（docker-compose 已配）。

---

## 8. 测试

```powershell
cd backend
uv run pytest tests/unit -v
uv run pytest tests/integration/test_material_extraction.py -v
```

smoke test：

```powershell
uv run python -m src.scripts.smoke_test_importer --src F:/PPT素材 --max-assets 5
```

---

## 9. 扩展点

| 想做的事 | 改哪里 |
| -------- | ------ |
| 加新 `visual_type` | `src/db/models/slide_asset.py` 的 `SlideVisualType` 枚举 + `classifier._KEYWORD_RULES` 加关键字 + LLM prompt 更新 |
| 换多模态供应商 | `_SYSTEM_PROMPT` + 必要时把 `LLMClient` 改成指向 DashScope / Anthropic / Ollama |
| 同步到向量库 | `importer._process_one` 已调 `ensure_embedding_for_asset`；换 embedding provider 改 `src/services/knowledge_base/embedder.py` |
| 走对象存储存原图（不只是缩略图） | `importer._process_one` 里 `original_key` 的写入逻辑；目前 key 写了但存的是缩略图字节——可改成缓存原图字节到 `ExtractedAsset.original_bytes` |
| 给素材打额外业务标签 | `ClassificationResult.industry_tags` 已能容纳 5 个以内；超过的话扩 dataclass + 改 LLM prompt |
