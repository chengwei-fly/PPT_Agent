"""One-shot bundler: copy the upstream SVG-to-PPTX engine into
``backend/src/integrations/ppt_engine/`` under the internal ``pptx_renderer``
package name and strip branded annotations.

Run with: ``python scripts/bundle_ppt_engine.py``

The package is renamed from the upstream ``svg_to_pptx`` to
``pptx_renderer`` to match the project's internal naming. File content
referring to the upstream skill or its repository is replaced with
neutral phrasing. The legacy internal module name ``svg_to_pptx`` is
also rewritten to ``pptx_renderer`` so no traces of the original name
remain in the bundled output.

Source path resolution (highest priority first):
  1. ``PPTAGENT_UPSTREAM_SKILL_DIR`` environment variable (absolute path
     to the upstream skill directory, i.e. the one that contains
     ``scripts/`` and ``references/``).
  2. A sibling repo at ``../<name>``, where ``<name>`` defaults to
     ``ppt-master`` but can be overridden with
     ``PPTAGENT_SIBLING_REPO_NAME`` (useful when the upstream lives in
     a differently-named checkout).
  3. The historical Windows-only default
     ``F:\\workspace\\ppt-master\\skills\\ppt-master`` — only honoured
     when ``PPTAGENT_ALLOW_LEGACY_PATH=1`` is set explicitly. This
     default exists purely for backward compatibility with the original
     developer setup; new contributors must set the env var.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DST = ROOT / "src" / "integrations" / "ppt_engine"

# Internal package name (matches the project's refactored naming).
INTERNAL_PACKAGE = "pptx_renderer"

DEFAULT_SIBLING_REPO_NAME = "ppt-master"
LEGACY_HARDCODED_PATH = Path(r"F:\workspace\ppt-master\skills\ppt-master")


def _resolve_source() -> Path:
    """Resolve the upstream skill directory.

    Resolution order:
        1. ``PPTAGENT_UPSTREAM_SKILL_DIR`` (absolute path).
        2. Sibling repo at ``<repo-root>/../<name>`` where ``<name>`` is
           ``PPTAGENT_SIBLING_REPO_NAME`` (default: ``ppt-master``).
        3. Legacy hardcoded path — opt-in via
           ``PPTAGENT_ALLOW_LEGACY_PATH=1``.

    Returns the resolved path, or raises ``FileNotFoundError`` with an
    actionable error message.
    """
    repo_root = ROOT.parent  # PPT_Agent/

    env_path = os.environ.get("PPTAGENT_UPSTREAM_SKILL_DIR")
    if env_path:
        candidate = Path(env_path).expanduser().resolve()
        if candidate.is_dir():
            return candidate
        raise FileNotFoundError(
            f"PPTAGENT_UPSTREAM_SKILL_DIR points to {candidate} but that "
            "directory does not exist."
        )

    sibling_name = os.environ.get(
        "PPTAGENT_SIBLING_REPO_NAME", DEFAULT_SIBLING_REPO_NAME
    )
    sibling_path = (repo_root.parent / sibling_name / "skills" / sibling_name).resolve()
    if sibling_path.is_dir():
        return sibling_path

    if os.environ.get("PPTAGENT_ALLOW_LEGACY_PATH") == "1" and LEGACY_HARDCODED_PATH.is_dir():
        print(
            "WARN: using legacy hardcoded upstream path "
            f"{LEGACY_HARDCODED_PATH}. Set PPTAGENT_UPSTREAM_SKILL_DIR "
            "(or PPTAGENT_SIBLING_REPO_NAME) to silence this warning."
        )
        return LEGACY_HARDCODED_PATH

    raise FileNotFoundError(
        "Could not locate the upstream skill directory. Tried:\n"
        f"  - PPTAGENT_UPSTREAM_SKILL_DIR env var (unset)\n"
        f"  - Sibling repo at {sibling_path}\n"
        f"  - Legacy path {LEGACY_HARDCODED_PATH} "
        "(requires PPTAGENT_ALLOW_LEGACY_PATH=1)\n"
        "Set PPTAGENT_UPSTREAM_SKILL_DIR to the absolute path of the "
        "upstream skill directory (the one containing scripts/ and "
        "references/)."
    )


SRC = _resolve_source()

# Patterns to strip from copied files (case-insensitive). These remove the
# upstream skill's branding and any links back to its repository, so the
# bundled renderer reads as neutral technical code.
BRAND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Upstream skill / repo branding → neutral phrasing.
    (re.compile(r"PPT[\s\-_]?Master", re.IGNORECASE), "internal rendering library"),
    (re.compile(r"ppt[\s\-_]?master", re.IGNORECASE), "internal rendering library"),
    (
        re.compile(r"github\.com/[^\s)>]*ppt[\s\-_]?master[^\s)<]*", re.IGNORECASE),
        "internal-renderer-repo",
    ),
    (
        re.compile(r"https?://[^\s)<>]*ppt[\s\-_]?master[^\s)<>]*", re.IGNORECASE),
        "internal-renderer-repo",
    ),
    # Legacy internal package name — the upstream subpackage was named
    # ``svg_to_pptx``; we ship it under ``pptx_renderer`` and rewrite
    # every reference (docstrings, ``__package__``, ``sys.modules``
    # registration, ``types.ModuleType(...)`` call, etc.) so no trace of
    # the original name leaks into the bundled output.
    (re.compile(r"\bsvg_to_pptx\b", re.IGNORECASE), "pptx_renderer"),
    (re.compile(r"\bsvg-to-pptx\b", re.IGNORECASE), "pptx-renderer"),
    (re.compile(r"\bsvg2pptx\b", re.IGNORECASE), "pptx_renderer"),
)


def scrub_text(text: str) -> str:
    for pattern, replacement in BRAND_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding="utf-8", errors="replace")
    text = scrub_text(text)
    dst.write_text(text, encoding="utf-8")


def copy_dir(src: Path, dst: Path, *, include_ext: tuple[str, ...]) -> list[Path]:
    copied: list[Path] = []
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in include_ext:
            continue
        rel = path.relative_to(src)
        target = dst / rel
        copy_file(path, target)
        copied.append(target)
    return copied


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: source not found: {SRC}", file=sys.stderr)
        return 1

    # Wipe any prior copy of the bundled engine (covers old svg_to_pptx/
    # layout from earlier runs).
    if DST.exists():
        print(f"Removing existing {DST}")
        shutil.rmtree(DST)
    DST.mkdir(parents=True)

    # 1) Copy the upstream package and rename to the internal package name.
    src_pkg = SRC / "scripts" / "svg_to_pptx"
    dst_pkg = DST / "scripts" / INTERNAL_PACKAGE
    if not src_pkg.exists():
        print(f"ERROR: source package missing: {src_pkg}", file=sys.stderr)
        return 1
    py_files = copy_dir(src_pkg, dst_pkg, include_ext=(".py",))
    print(f"Copied {len(py_files)} Python files -> {dst_pkg}")

    # 2) Copy the references/ folder (visual-styles, modes, shared-standards).
    src_refs = SRC / "references"
    dst_refs = DST / "references"
    md_files: list[Path] = []
    for sub in ("visual-styles", "modes"):
        for src_md in (src_refs / sub).glob("*.md"):
            if src_md.name.startswith("_"):
                continue  # skip _index.md navigation files
            target = dst_refs / sub / src_md.name
            copy_file(src_md, target)
            md_files.append(target)
    shared = src_refs / "shared-standards.md"
    if shared.exists():
        copy_file(shared, dst_refs / "shared-standards.md")
        md_files.append(dst_refs / "shared-standards.md")
    print(f"Copied {len(md_files)} markdown references -> {dst_refs}")

    # 3) Top-level package markers.
    (DST / "scripts" / "__init__.py").write_text(
        '"""Internal rendering library (neutral branding)."""\n',
        encoding="utf-8",
    )
    (DST / "references" / "__init__.py").write_text(
        '"""Bundled reference documents (visual styles, modes, shared standards)."""\n',
        encoding="utf-8",
    )

    print()
    print("Done. Bundled renderer root:", DST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
