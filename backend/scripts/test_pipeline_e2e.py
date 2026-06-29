"""End-to-end test: pipeline-equivalent SVG → PPTX conversion.

Simulates what the LLM-driven general-mode pipeline would produce and
verifies the bundled renderer produces a non-blank PPTX. This is the
exact failure mode reported by users (3-slide PPTX with only title
outlines, pages white empty).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Provide minimal env so settings can be loaded (we don't actually
# touch DB/MinIO in this test — we only exercise the renderer).
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost:5432/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x:x@localhost:5432/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("S3_ENDPOINT", "localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "minioadmin")
os.environ.setdefault("S3_SECRET_KEY", "minioadmin")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-padding")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# Avoid pulling in backend settings (.env may not be configured)
import importlib

bridge_mod = importlib.import_module("src.integrations.pptx_render_bridge")
print("=== End-to-End Pipeline Test ===\n")
print("Bridge health check:")
for k, v in bridge_mod.health_check().items():
    print(f"  {k}: {v}")

# 1) Reference loader resolves the bundled references
ref_loader_mod = importlib.import_module("src.services.generation.reference_loader")
ref_loader = ref_loader_mod.ReferenceLoader()
shared = ref_loader.load_shared_standards()
print(f"\nshared-standards: {len(shared)} chars  ok={bool(shared)}")
style = ref_loader.load_visual_style("swiss-minimal")
print(f"visual-style swiss-minimal: {len(style) if style else 0} chars  ok={bool(style)}")
mode = ref_loader.load_communication_mode("pyramid")
print(f"mode pyramid: {len(mode) if mode else 0} chars  ok={bool(mode)}")
assert shared and style and mode, "reference loader missing content"

# 2) Three SVG slides that look like what the LLM would emit
SLIDES = [
    {
        "order": 1,
        "title": "2026 战略汇报",
        "svg": """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">
  <rect width="1280" height="720" fill="#FFFFFF"/>
  <rect x="0" y="0" width="1280" height="120" fill="#0B2545"/>
  <text x="80" y="80" font-family="Arial" font-size="48" font-weight="bold" fill="#FFFFFF">2026 战略汇报</text>
  <text x="80" y="200" font-family="Arial" font-size="24" fill="#13315C">增长路径与组织升级方案</text>
  <line x1="80" y1="240" x2="200" y2="240" stroke="#F4A261" stroke-width="6"/>
  <text x="80" y="650" font-family="Arial" font-size="18" fill="#8DA9C4">汇报人 · 增长战略部 · 2026.06</text>
</svg>""",
    },
    {
        "order": 2,
        "title": "目录",
        "svg": """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">
  <rect width="1280" height="720" fill="#FFFFFF"/>
  <text x="80" y="80" font-family="Arial" font-size="36" font-weight="bold" fill="#0B2545">目录</text>
  <line x1="80" y1="100" x2="200" y2="100" stroke="#F4A261" stroke-width="4"/>
  <g font-family="Arial" font-size="22" fill="#1A1A1A">
    <text x="120" y="180">01  战略背景与挑战</text>
    <text x="120" y="240">02  增长路径设计</text>
    <text x="120" y="300">03  关键举措拆解</text>
    <text x="120" y="360">04  资源与里程碑</text>
    <text x="120" y="420">05  风险与保障</text>
    <text x="120" y="480">06  预期成果与展望</text>
  </g>
</svg>""",
    },
    {
        "order": 3,
        "title": "增长路径总览",
        "svg": """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">
  <rect width="1280" height="720" fill="#FFFFFF"/>
  <text x="80" y="80" font-family="Arial" font-size="36" font-weight="bold" fill="#0B2545">增长路径总览</text>
  <line x1="80" y1="100" x2="200" y2="100" stroke="#F4A261" stroke-width="4"/>
  <g>
    <rect x="80"  y="180" width="220" height="120" rx="12" fill="#E0FBFC"/>
    <text x="190" y="230" font-family="Arial" font-size="22" font-weight="bold" fill="#0B2545" text-anchor="middle">渠道</text>
    <text x="190" y="270" font-family="Arial" font-size="18" fill="#3D5A80" text-anchor="middle">公私域联动</text>
    <rect x="380" y="180" width="220" height="120" rx="12" fill="#E0FBFC"/>
    <text x="490" y="230" font-family="Arial" font-size="22" font-weight="bold" fill="#0B2545" text-anchor="middle">产品</text>
    <text x="490" y="270" font-family="Arial" font-size="18" fill="#3D5A80" text-anchor="middle">差异化矩阵</text>
    <rect x="680" y="180" width="220" height="120" rx="12" fill="#E0FBFC"/>
    <text x="790" y="230" font-family="Arial" font-size="22" font-weight="bold" fill="#0B2545" text-anchor="middle">运营</text>
    <text x="790" y="270" font-family="Arial" font-size="18" fill="#3D5A80" text-anchor="middle">数据驱动</text>
    <rect x="980" y="180" width="220" height="120" rx="12" fill="#F4A261"/>
    <text x="1090" y="230" font-family="Arial" font-size="22" font-weight="bold" fill="#FFFFFF" text-anchor="middle">目标</text>
    <text x="1090" y="270" font-family="Arial" font-size="18" fill="#FFFFFF" text-anchor="middle">收入 +30%</text>
  </g>
  <text x="80" y="420" font-family="Arial" font-size="20" fill="#3D5A80">三大抓手协同发力，确保 2026 全年增长目标达成</text>
</svg>""",
    },
]

# 3) Write to temp dir, then invoke the renderer directly
def _main() -> None:
    with tempfile.TemporaryDirectory(prefix="pptagent_e2e_") as tmp:
        tmp_path = Path(tmp)
        svg_dir = tmp_path / "svg"
        svg_dir.mkdir()
        out = tmp_path / "out.pptx"
        svg_paths = []
        for s in SLIDES:
            p = svg_dir / f"{s['order']:02d}.svg"
            p.write_text(s["svg"], encoding="utf-8")
            svg_paths.append(p)

        ok = bridge_mod.create_pptx_with_native_svg(
            svg_files=svg_paths,
            output_path=out,
            canvas_format="169",
            verbose=False,
            notes=None,
            enable_notes=False,
            use_native_shapes=False,
            use_compat_mode=True,
        )
        assert ok, "renderer returned False"
        assert out.is_file(), "PPTX not written"
        data = out.read_bytes()
        assert data[:2] == b"PK", "PPTX header wrong"
        assert len(data) > 10_000, f"PPTX suspiciously small: {len(data)} bytes"

        # 4) Decompose the PPTX to verify slide content (not just titles).
        #    use_compat_mode=True embeds the SVG as a <p:pic> (PNG + SVG
        #    fallback). The visible content lives in the image, not in
        #    native <a:t> runs — so we validate the image payload.
        import zipfile
        import re

        with zipfile.ZipFile(out) as zf:
            slide_files = [n for n in zf.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
            assert len(slide_files) == 3, f"expected 3 slides, got {len(slide_files)}"
            png_files = sorted(n for n in zf.namelist() if re.match(r"ppt/media/image\d+\.png$", n))
            svg_files = sorted(n for n in zf.namelist() if re.match(r"ppt/media/image\d+\.svg$", n))
            print(f"  slides: {len(slide_files)}, png: {len(png_files)}, svg: {len(svg_files)}")
            assert len(png_files) == 3, f"expected 3 PNG embeds, got {len(png_files)}"
            assert len(svg_files) == 3, f"expected 3 SVG embeds, got {len(svg_files)}"
            # Each PNG should be a real, non-blank raster (>= 5KB)
            for n in png_files:
                size = zf.getinfo(n).file_size
                print(f"    {n}: {size:,} bytes")
                assert size > 5_000, f"{n} suspiciously small ({size} bytes) — likely blank"
            # Each SVG should carry the original markup (text + shapes)
            for n in svg_files:
                svg = zf.read(n).decode("utf-8")
                assert "<text" in svg, f"{n} missing <text> element"
                assert "svg" in svg.lower(), f"{n} missing svg root"
            # Each slide XML should contain a <p:pic> reference to a media file
            for n in slide_files:
                xml = zf.read(n).decode("utf-8")
                assert "<p:pic>" in xml, f"{n} has no picture shape — looks blank"
                # title text in image, not in slide XML — that's expected for compat mode
            print(f"\n  pptx size: {len(data):,} bytes")
            # Spot-check that the title from the first slide shows up in the
            # embedded SVG (i.e. the image really carries the content).
            first_svg = zf.read(svg_files[0]).decode("utf-8")
            assert "2026 战略汇报" in first_svg, "first slide title missing from embedded SVG"
            assert "增长路径与组织升级方案" in first_svg, "first slide subtitle missing"
            print("  first slide content found in embedded SVG: OK")

    print("\nE2E OK: 3-slide PPTX generated with real, non-blank content.")


if __name__ == "__main__":
    # multiprocessing on Windows requires this guard
    from multiprocessing import freeze_support
    freeze_support()
    _main()
