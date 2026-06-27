"""Tools package — Agent-callable tools for generation, parsing, etc.

Each tool follows the standard tool interface:
- `name`: str
- `description`: str
- `parameters`: dict (JSON schema)
- `func`: async callable

Uses lazy imports to avoid circular dependency issues.
"""


def __getattr__(name: str):
    """Lazy import tools to avoid circular dependencies."""
    tool_map = {
        "KnowledgeRetriever": "src.tools.knowledge_retriever",
        "PIIDetectorTool": "src.tools.pii_detector",
        "SampleParserTool": "src.tools.sample_parser",
        "StyleNormalizer": "src.tools.style_normalizer",
        "SVG2PPTXTool": "src.tools.svg2pptx",
    }
    if name in tool_map:
        import importlib

        module = importlib.import_module(tool_map[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "KnowledgeRetriever",
    "PIIDetectorTool",
    "SVG2PPTXTool",
    "SampleParserTool",
    "StyleNormalizer",
]
