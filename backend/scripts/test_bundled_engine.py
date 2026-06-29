"""Smoke test for the bundled SVG-to-PPTX rendering library.

Avoids importing the backend's settings module so the test runs without
``.env``. Verifies:

  1. The bundled ``pptx_renderer`` package is importable.
  2. ``create_pptx_with_native_svg`` builds a valid PPTX.
  3. Reference markdown files load (visual-styles, modes, shared-standards).
  4. No upstream branding leaks into copied content.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_SCRIPTS = REPO_ROOT / "src" / "integrations" / "ppt_engine" / "scripts"
BUNDLED_REFERENCES = (
    REPO_ROOT / "src" / "integrations" / "ppt_engine" / "references"
)
INTERNAL_PACKAGE = "pptx_renderer"

if not BUNDLED_SCRIPTS.is_dir():
    print(f"FAIL: bundled scripts dir missing: {BUNDLED_SCRIPTS}")
    sys.exit(1)

sys.path.insert(0, str(BUNDLED_SCRIPTS))
import pptx_renderer  # noqa: E402

print("=== Bundled SVG-to-PPTX Rendering Library Smoke Test ===\n")
print(f"Renderer root : {BUNDLED_SCRIPTS.parent}")
print(f"References    : {BUNDLED_REFERENCES}")
print(f"create_pptx_with_native_svg : {hasattr(pptx_renderer, 'create_pptx_with_native_svg')}")
print(f"convert_svg_to_slide_shapes : {hasattr(pptx_renderer, 'convert_svg_to_slide_shapes')}\n")
assert hasattr(pptx_renderer, "create_pptx_with_native_svg"), "missing API"
assert hasattr(pptx_renderer, "convert_svg_to_slide_shapes"), "missing API"


# --- 2) Reference markdown files -----------------------------------------
SHARED = BUNDLED_REFERENCES / "shared-standards.md"
assert SHARED.is_file(), f"shared-standards.md missing at {SHARED}"
shared_text = SHARED.read_text(encoding="utf-8")
print(f"shared-standards.md: {len(shared_text)} chars  "
      f"(upstream 'ppt master' occurrences: "
      f"{shared_text.lower().count('ppt master')})")
assert "PPT Master" not in shared_text, "shared-standards still contains PPT Master"
assert "ppt master" not in shared_text, "shared-standards still contains ppt master"
assert shared_text, "shared-standards is empty"

styles_dir = BUNDLED_REFERENCES / "visual-styles"
expected_styles = [
    "blueprint", "brutalist", "chalkboard", "dark-tech", "data-journalism",
    "editorial", "glassmorphism", "ink-notes", "ink-wash", "memphis",
    "paper-cut", "photo-editorial", "pixel-art", "sketch-notes",
    "soft-rounded", "swiss-minimal", "vintage-poster", "zine",
]
missing = [s for s in expected_styles if not (styles_dir / f"{s}.md").exists()]
assert not missing, f"missing style files: {missing}"
print(f"visual-styles: {len(expected_styles)} files OK")

modes_dir = BUNDLED_REFERENCES / "modes"
expected_modes = ["briefing", "instructional", "narrative", "pyramid", "showcase"]
missing = [m for m in expected_modes if not (modes_dir / f"{m}.md").exists()]
assert not missing, f"missing mode files: {missing}"
print(f"modes: {len(expected_modes)} files OK\n")


# --- 3) Build a PPTX from a real SVG -------------------------------------
SAMPLE_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">
  <rect width="1280" height="720" fill="#FFFFFF"/>
  <rect x="0" y="0" width="1280" height="10" fill="#1A73E8"/>
  <text x="80" y="100" font-family="Arial" font-size="48" font-weight="bold" fill="#1A1A1A">Bundled Renderer Test</text>
  <text x="80" y="180" font-family="Arial" font-size="24" fill="#333333">Smoke-test slide produced by the embedded renderer.</text>
  <g id="card-metric">
    <rect x="80" y="260" width="320" height="200" rx="16" fill="#F5F7FA"/>
    <text x="100" y="320" font-family="Arial" font-size="20" fill="#6E6E73">Latency</text>
    <text x="100" y="380" font-family="Arial" font-size="56" font-weight="bold" fill="#1A73E8">120<tspan font-size="28" fill="#6E6E73">ms</tspan></text>
  </g>
  <g id="card-metric-2">
    <rect x="440" y="260" width="320" height="200" rx="16" fill="#F5F7FA"/>
    <text x="460" y="320" font-family="Arial" font-size="20" fill="#6E6E73">Conversion</text>
    <text x="460" y="380" font-family="Arial" font-size="56" font-weight="bold" fill="#34A853">+18.4%</text>
  </g>
</svg>
"""


with tempfile.TemporaryDirectory(prefix="ppt_renderer_test_") as tmp:
    tmp_path = Path(tmp)
    svg1 = tmp_path / "01.svg"
    svg1.write_text(SAMPLE_SVG, encoding="utf-8")
    slide2 = SAMPLE_SVG.replace(
        "Bundled Renderer Test", "Second Slide", 1
    ).replace(
        "Smoke-test slide produced by the embedded renderer.",
        "Confirms multi-slide conversion works.",
    )
    svg2 = tmp_path / "02.svg"
    svg2.write_text(slide2, encoding="utf-8")
    out = tmp_path / "out.pptx"
    ok = pptx_renderer.create_pptx_with_native_svg(
        svg_files=[svg1, svg2],
        output_path=out,
        canvas_format="169",
        verbose=False,
        use_compat_mode=True,
    )
    assert ok, "create_pptx_with_native_svg returned False"
    assert out.is_file(), "PPTX not written"
    data = out.read_bytes()
    assert data[:2] == b"PK", f"PPTX header wrong: {data[:8]!r}"
    assert len(data) > 5_000, f"PPTX too small: {len(data)} bytes"
    print(f"PPTX written: {out}  ({len(data):,} bytes, 2 slides)")

# --- 4) Make sure no upstream branding leaked into copied Python content.
import subprocess
scan = subprocess.run(
    [sys.executable, "-c",
     "import pathlib, re, sys; "
     f"root = pathlib.Path(r'{BUNDLED_SCRIPTS}'); "
     "hits = [str(p) for p in root.rglob('*.py') if re.search(r'(?i)ppt[\\s\\-_]?master', p.read_text(encoding='utf-8', errors='replace'))]; "
     "sys.exit(0 if not hits else 1)"],
    capture_output=True, text=True,
)
if scan.returncode != 0:
    print("FAIL: upstream branding leaked into Python files")
    raise SystemExit(1)
print("Brand scrub: no 'PPT Master' references in any bundled .py file.")

print("\nAll smoke tests passed.")
