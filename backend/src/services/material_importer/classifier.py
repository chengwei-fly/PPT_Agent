"""Material classifier — visual_type + industry_tags + title.

Two strategies:

* :class:`LLMClassifier`  — multimodal LLM (gpt-4o, qwen-vl-max, etc.)
* :class:`HeuristicClassifier` — deterministic, no LLM, works offline

The :func:`classify_asset` factory picks the right one based on whether
``OPENAI_API_KEY`` is configured (or another multimodal endpoint).

The classifier never raises — on failure it returns a safe
``(visual_type='mixed', industry_tags=[], title=None)`` tuple so the import
loop can keep going.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable
from dataclasses import dataclass, field

from src.core.config import settings
from src.core.observability import get_logger
from src.db.models import SlideVisualType
from src.services.material_importer.extractor import ExtractedAsset

logger = get_logger("material_importer.classifier")

# ── Allowed values for LLM prompt — keep in sync with the enum ──────
ALLOWED_VISUAL_TYPES = [vt.value for vt in SlideVisualType]
# Hard cap on tag count to avoid garbage from over-eager LLMs
MAX_TAGS = 5
MAX_TITLE_LEN = 60


# ────────────────────────────────────────────────────────────────────
# Result type
# ────────────────────────────────────────────────────────────────────


@dataclass
class ClassificationResult:
    visual_type: SlideVisualType = SlideVisualType.mixed
    title: str | None = None
    industry_tags: list[str] = field(default_factory=list)
    rationale: str = ""
    used: str = "heuristic"  # 'llm' | 'heuristic'


# ────────────────────────────────────────────────────────────────────
# Classifier interface
# ────────────────────────────────────────────────────────────────────


class MaterialClassifier:
    async def classify(self, asset: ExtractedAsset) -> ClassificationResult:  # pragma: no cover
        raise NotImplementedError


# ────────────────────────────────────────────────────────────────────
# Heuristic (offline) classifier
# ────────────────────────────────────────────────────────────────────


# Keyword → visual_type mapping. Order matters: more specific patterns first.
_KEYWORD_RULES: list[tuple[re.Pattern[str], SlideVisualType]] = [
    # Cover
    (re.compile(r"封面|cover|公司|品牌|产品|品牌介绍|汇报|路演", re.I), SlideVisualType.cover),
    # Closing
    (re.compile(r"谢谢|thank|结束|结尾|q&a|问答|答疑|contact|联系", re.I), SlideVisualType.closing),
    # TOC
    (re.compile(r"目录|agenda|contents|索引|大纲|章节", re.I), SlideVisualType.toc),
    # Architecture — Chinese/English keywords
    (re.compile(r"架构|architecture|微服务|microservice|系统架构|tech.?stack|技术栈|模块", re.I), SlideVisualType.architecture),
    # Flowchart
    (re.compile(r"流程|flow|workflow|管道|pipeline|步骤|过程|时序|sequence|节点", re.I), SlideVisualType.flowchart),
    # Data
    (re.compile(r"数据|data|chart|图表|柱状|饼图|趋势|增长|占比|统计|报表|metrics|kpi", re.I), SlideVisualType.data),
    # Body / general
    (re.compile(r"亮点|优势|特点|方案|规划|总结|介绍|说明|背景|现状|痛点|价值", re.I), SlideVisualType.body),
]


# Keywords for industry_tags extraction
_TAG_KEYWORDS: dict[str, list[str]] = {
    "物流": ["物流", "logistic", "运输", "配送", "供应链", "supply chain", "快递", "仓储"],
    "地图": ["地图", "中国", "省份", "省市", "world", "map", "全国", "全球", "中国地图", "世界地图"],
    "图标": ["图标", "icon", "pictogram", "按钮", "symbol"],
    "关系图": ["关系", "relationship", "层级", "hierarchy", "组织", "structure"],
    "流程图": ["流程", "flow", "pipeline", "workflow", "步骤", "时序"],
    "架构图": ["架构", "architecture", "microservice", "微服务", "tech", "stack"],
    "数据图": ["数据", "data", "chart", "graph", "柱状", "饼图", "趋势"],
    "模板": ["模板", "template", "罗兰贝格", "roland berger", "咨询", "麦肯锡", "mckinsey", "经典"],
    "图标库": ["汇总", "collection", "大全", "icon", "图标库"],
    "封面": ["封面", "cover", "title", "首页"],
    "结尾": ["结尾", "谢谢", "thank", "closing"],
    "目录": ["目录", "toc", "agenda", "index"],
}


class HeuristicClassifier(MaterialClassifier):
    """Pure-Python classifier. No LLM, no network."""

    async def classify(self, asset: ExtractedAsset) -> ClassificationResult:
        # Concatenate all the text signals we have
        haystack = " ".join(
            [
                asset.source_file,
                asset.title_hint,
                asset.text,
            ]
        )

        # visual_type: walk the rules; first match wins. If none match,
        # we try to infer from shape/image characteristics.
        visual_type = SlideVisualType.mixed
        for pat, vt in _KEYWORD_RULES:
            if pat.search(haystack):
                visual_type = vt
                break

        # Pure-image icons → cover/mixed. Use aspect ratio + colour count
        # as a weak signal: very wide thumbnails with no text are usually
        # banner-style icons.
        if visual_type == SlideVisualType.mixed and not asset.text.strip():
            if asset.width > 0 and asset.height > 0:
                ratio = asset.width / asset.height
                if 0.8 < ratio < 1.4 and len(asset.palette) <= 3:
                    # Square icon with few colours → probably an icon
                    visual_type = SlideVisualType.body

        # industry_tags: scan keyword table
        tags: list[str] = []
        for tag, words in _TAG_KEYWORDS.items():
            if any(w.lower() in haystack.lower() for w in words):
                tags.append(tag)
                if len(tags) >= MAX_TAGS:
                    break

        # Title: prefer slide's title text, else first non-empty text chunk
        title: str | None = None
        if asset.title_hint:
            title = asset.title_hint
        elif asset.text:
            first = asset.text.split("|")[0].strip()
            if first:
                title = first
        if title:
            title = title[:MAX_TITLE_LEN]

        return ClassificationResult(
            visual_type=visual_type,
            title=title,
            industry_tags=tags,
            rationale="heuristic: keyword matching",
            used="heuristic",
        )


# ────────────────────────────────────────────────────────────────────
# LLM-based classifier
# ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """你是 PPT 素材分类助手。请根据缩略图判断它属于哪类素材页面，
并给出 3-5 个中文行业标签（短词，1-4 字）。

严格按 JSON 格式输出（不要任何解释、不要 markdown 代码块）:
{
  "visual_type": "cover|toc|architecture|flowchart|data|body|closing|mixed",
  "title": "不超过 30 字的中文短句",
  "industry_tags": ["标签1", "标签2", "标签3"],
  "rationale": "20 字以内的判断理由"
}

visual_type 取值说明:
- cover: 封面/标题页
- toc: 目录/索引
- architecture: 架构图、技术栈、系统模块图
- flowchart: 流程图、时序图、节点关系图、漏斗、管道
- data: 数据图、柱状/饼图/折线、统计、指标
- body: 正文/说明/总结/方案等纯文字页
- closing: 结尾/致谢/Q&A
- mixed: 不确定或综合内容

industry_tags 示例: 物流、地图、图标、关系图、流程图、架构图、模板、PPT 模板、图标库
"""


class LLMClassifier(MaterialClassifier):
    """Multimodal LLM classifier. Requires a vision-capable model."""

    def __init__(self, model: str | None = None) -> None:
        from src.services.generation.llm_client import LLMClient

        self._client = LLMClient(model=model)

    async def classify(self, asset: ExtractedAsset) -> ClassificationResult:
        user_text = (
            f"源文件: {asset.source_file}\n"
            f"原始标题: {asset.title_hint or '(无)'}\n"
            f"页面文字: {asset.text[:300] or '(无文字)'}"
        )
        try:
            data = await self._client.complete_json_vision(
                system_prompt=_SYSTEM_PROMPT,
                user_text=user_text,
                image_bytes=asset.image_bytes,
                image_mime=asset.image_mime or "image/jpeg",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "llm_classify_failed",
                file=asset.source_file,
                slide=asset.slide_index,
                error=str(e),
            )
            return ClassificationResult(rationale=f"llm_failed: {e}", used="llm-failed")

        # Parse visual_type
        vt_raw = (data.get("visual_type") or "").strip().lower()
        try:
            visual_type = SlideVisualType(vt_raw)
        except ValueError:
            visual_type = SlideVisualType.mixed

        title = data.get("title") or None
        if title:
            title = str(title)[:MAX_TITLE_LEN].strip() or None

        raw_tags = data.get("industry_tags") or []
        if isinstance(raw_tags, str):
            raw_tags = [t.strip() for t in re.split(r"[,，、;；\s]+", raw_tags) if t.strip()]
        elif not isinstance(raw_tags, list):
            raw_tags = []
        tags: list[str] = []
        for t in raw_tags:
            s = str(t).strip()
            if s and s not in tags and len(s) <= 16:
                tags.append(s)
            if len(tags) >= MAX_TAGS:
                break

        return ClassificationResult(
            visual_type=visual_type,
            title=title,
            industry_tags=tags,
            rationale=str(data.get("rationale", ""))[:120],
            used="llm",
        )


# ────────────────────────────────────────────────────────────────────
# Factory
# ────────────────────────────────────────────────────────────────────


def classify_asset(
    asset: ExtractedAsset,
    prefer_llm: bool = True,
    llm_model: str | None = None,
) -> "Awaitable[ClassificationResult]":
    """Async factory — picks LLM when available + preferred, else heuristic.

    Returns a coroutine the caller must ``await``. Returning a coroutine
    (rather than awaiting here) lets importers fan out many classifications
    in parallel via ``asyncio.gather``.
    """
    if prefer_llm and _llm_available():
        cls: MaterialClassifier = LLMClassifier(model=llm_model)
    else:
        cls = HeuristicClassifier()
    return cls.classify(asset)


def _llm_available() -> bool:
    """True when an LLM endpoint with an API key is configured."""
    key = (settings.openai_api_key or "").strip()
    return bool(key and key != "sk-replace")


# ────────────────────────────────────────────────────────────────────
# Cache helper
# ────────────────────────────────────────────────────────────────────


def make_cached_classify(
    prefer_llm: bool = True,
    llm_model: str | None = None,
):
    """Return an async function that classifies with an in-process LRU cache.

    Cache key = (source_file, slide_index, shape_name, image_hash).
    Image hash is cheap and prevents collisions when the same slide is
    re-classified after edits.
    """
    import hashlib

    cache: dict[tuple[str, int, str, str], ClassificationResult] = {}
    max_size = 4096

    async def _classify(asset: ExtractedAsset) -> ClassificationResult:
        img_hash = hashlib.sha256(asset.image_bytes).hexdigest()[:16]
        key = (asset.source_file, asset.slide_index, asset.shape_name, img_hash)
        cached = cache.get(key)
        if cached is not None:
            return cached
        if prefer_llm and _llm_available():
            cls: MaterialClassifier = LLMClassifier(model=llm_model)
        else:
            cls = HeuristicClassifier()
        result = await cls.classify(asset)
        if len(cache) >= max_size:
            cache.pop(next(iter(cache)))
        cache[key] = result
        return result

    return _classify


# Re-export for convenience
__all__ = [
    "ClassificationResult",
    "MaterialClassifier",
    "HeuristicClassifier",
    "LLMClassifier",
    "classify_asset",
    "make_cached_classify",
]
